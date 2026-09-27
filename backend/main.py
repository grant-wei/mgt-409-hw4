from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import os
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from pwdlib import PasswordHash
from pydantic_ai import UsageLimits

from agent import shop_agent
from audit import new_entry, tool_calls_from, write_audit_entry
from models import ChatDependencies, ChatHistoryMessage, ChatHistoryResponse, ChatProductCard, ChatRequest, ChatResponse, ProductComparisonItem, ProductSummary
from tools import load_catalogue


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE = PROJECT_ROOT / "data" / "campus_customs.db"
SESSION_COOKIE = "campus_customs_session"
SESSION_LIFETIME = 12 * 60 * 60
COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").casefold() == "true"

password_hasher = PasswordHash.recommended()
dummy_password_hash = password_hasher.hash(secrets.token_urlsafe(24))

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_sessions()
    yield


app = FastAPI(title="Campus Customs API", lifespan=lifespan)


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=1024)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: EmailStr


class AuthResponse(BaseModel):
    user: UserResponse


def connect() -> sqlite3.Connection:
    if not DATABASE.is_file():
        raise RuntimeError(f"Database not found at {DATABASE}")
    connection = sqlite3.connect(DATABASE, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database() -> Iterator[sqlite3.Connection]:
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_sessions() -> None:
    with database() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            )
            """
        )


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def public_user(row: sqlite3.Row) -> UserResponse:
    first_name = row["first_name"] or row["name"].split(" ", 1)[0]
    last_name = row["last_name"] or row["name"].partition(" ")[2]
    return UserResponse(
        id=row["id"],
        first_name=first_name,
        last_name=last_name,
        email=row["email"],
    )


def verify_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    """Return (matches, needs_rehash) and support the seeded legacy PBKDF2 rows."""
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            scheme, salt, expected = stored_hash.split("$", 2)
        except ValueError:
            return False, False
        if scheme != "pbkdf2_sha256":
            return False, False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
        ).hex()
        return hmac.compare_digest(actual, expected), True

    try:
        return password_hasher.verify(password, stored_hash), False
    except (ValueError, TypeError):
        return False, False


def set_session_cookie(response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = int(time.time()) + SESSION_LIFETIME
    with database() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, expires_at),
        )
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_LIFETIME,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def user_for_session(request: Request) -> UserResponse | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with database() as connection:
        row = connection.execute(
            """
            SELECT users.id, users.name, users.first_name, users.last_name, users.email
            FROM sessions JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
            """,
            (token_hash, int(time.time())),
        ).fetchone()
    return public_user(row) if row else None


def chat_constraints(message: str, catalogue: dict[str, ProductSummary]) -> tuple[str | None, str | None, float | None, bool, bool]:
    sizes = sorted(
        {stock.size for product in catalogue.values() for stock in product.sizes},
        key=len,
        reverse=True,
    )
    requested_size = next(
        (size for size in sizes if re.search(rf"(?<![A-Z0-9]){re.escape(size)}(?![A-Z0-9])", message, re.I)),
        None,
    )
    budget_match = re.search(
        r"\b(?:under|below|less than|up to|at most|max(?:imum)?(?: price| budget)?|budget(?: of)?)\s*\$?\s*(\d+(?:\.\d{1,2})?)",
        message,
        re.I,
    )
    max_price = float(budget_match.group(1)) if budget_match else None
    exclusive_price = bool(budget_match and re.match(r"\s*(under|below|less than)\b", message[budget_match.start():], re.I))

    known_colors = sorted(
        {color for product in catalogue.values() for color in product.colors},
        key=len,
        reverse=True,
    )
    color_terms = ["black", "blue", "navy", "white", "red", "gray", "grey", "green", "yellow", "purple", "pink", "orange", "brown", "maroon", "gold", "silver", "cream"]
    requested_color = next(
        (color for color in known_colors if re.search(rf"(?<!\w){re.escape(color)}(?!\w)", message, re.I)),
        None,
    )
    if requested_color is None:
        requested_color = next(
            (color for color in color_terms if re.search(rf"(?<!\w){re.escape(color)}(?!\w)", message, re.I)),
            None,
        )
    out_of_stock = bool(re.search(r"\b(out of stock|unavailable|not in stock)\b", message, re.I))
    return requested_size, requested_color, max_price, exclusive_price, out_of_stock


def satisfies_chat_constraints(product: ProductSummary, constraints: tuple[str | None, str | None, float | None, bool, bool]) -> bool:
    requested_size, requested_color, max_price, exclusive_price, out_of_stock = constraints
    if max_price is not None and (product.price >= max_price if exclusive_price else product.price > max_price):
        return False
    if requested_color and not any(requested_color.casefold() in color.casefold() for color in product.colors):
        return False
    if requested_size:
        matching_size = next((stock for stock in product.sizes if stock.size.casefold() == requested_size.casefold()), None)
        if matching_size is None or (matching_size.quantity == 0) != out_of_stock:
            return False
    else:
        has_available_size = any(stock.in_stock for stock in product.sizes)
        if has_available_size == out_of_stock:
            return False
    return True


def comparison_candidates(message: str, catalogue: dict[str, ProductSummary], constraints: tuple[str | None, str | None, float | None, bool, bool]) -> list[str]:
    lowered = message.casefold()
    explicit = [
        product for product in catalogue.values()
        if product.name.casefold() in lowered or product.product_id.casefold() in lowered
    ]
    if len(explicit) >= 2:
        return [product.product_id for product in explicit[:2] if satisfies_chat_constraints(product, constraints)]

    words = re.findall(r"[a-z0-9]+", lowered)
    ignored = {"compare", "comparison", "two", "both", "product", "products", "item", "items", "please", "the", "a", "an", "and", "or", "of", "for", "me", "show", "side", "by", "vs", "versus"}
    search_terms = {word for word in words if word not in ignored and len(word) > 1}
    search_terms.update(word[:-1] for word in words if word.endswith("ies") and len(word) > 3)
    ranked: list[tuple[int, str, ProductSummary]] = []
    for product in catalogue.values():
        if not satisfies_chat_constraints(product, constraints):
            continue
        name = product.name.casefold()
        details = " ".join((product.garment_type, product.description, *product.search_tags)).casefold()
        score = sum(3 for term in search_terms if term in name) + sum(1 for term in search_terms if term in details)
        if score:
            ranked.append((score, product.name.casefold(), product))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [product.product_id for _, _, product in ranked[:2]]


@app.post("/api/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response) -> AuthResponse:
    first_name = payload.first_name.strip()
    last_name = payload.last_name.strip()
    email = normalize_email(str(payload.email))
    if not first_name or not last_name:
        raise HTTPException(status_code=422, detail="First and last name are required.")

    password_hash = password_hasher.hash(payload.password)
    try:
        with database() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (name, email, password_hash, first_name, last_name)
                VALUES (?, ?, ?, ?, ?)
                """,
                (f"{first_name} {last_name}", email, password_hash, first_name, last_name),
            )
            row = connection.execute(
                "SELECT id, name, first_name, last_name, email FROM users WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="An account with that email already exists.") from exc

    set_session_cookie(response, row["id"])
    return AuthResponse(user=public_user(row))


@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response) -> AuthResponse:
    email = normalize_email(str(payload.email))
    with database() as connection:
        row = connection.execute(
            "SELECT id, name, first_name, last_name, email, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if row is None:
            password_hasher.verify(payload.password, dummy_password_hash)
            raise HTTPException(status_code=401, detail="Email or password is incorrect.")

        matches, needs_rehash = verify_password(payload.password, row["password_hash"])
        if not matches:
            raise HTTPException(status_code=401, detail="Email or password is incorrect.")

        if needs_rehash:
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hasher.hash(payload.password), row["id"]),
            )

    set_session_cookie(response, row["id"])
    return AuthResponse(user=public_user(row))


@app.get("/api/auth/me", response_model=AuthResponse)
def current_user(request: Request) -> AuthResponse:
    user = user_for_session(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Log in to continue.")
    return AuthResponse(user=user)


@app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with database() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Enter a message to chat.")
    if shop_agent is None:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY or OPENAI_MODEL is unavailable in the assignments .env file.",
        )

    user = user_for_session(request)
    catalogue = {product.product_id: product for product in load_catalogue(str(DATABASE))}
    page = payload.current_page.split("?", 1)[0].split("#", 1)[0]
    if not page.startswith("/") or page.startswith("//"):
        page = "/"
    current_product = None
    match = re.fullmatch(r"/products/([^/]+)/?", page)
    if match:
        from urllib.parse import unquote
        product_id = unquote(match.group(1))
        current_product = next((p for p in catalogue.values() if p.product_id == product_id), None)
    history = []
    if user is not None:
        from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

        with database() as connection:
            rows = connection.execute(
                "SELECT role, content FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT 12",
                (user.id,),
            ).fetchall()
        for row in reversed(rows):
            if row["role"] == "user":
                history.append(ModelRequest(parts=[UserPromptPart(content=row["content"])]))
            elif row["role"] == "assistant":
                history.append(ModelResponse(parts=[TextPart(content=row["content"])]))

    run_tool_calls: list[dict] = []
    try:
        result = await asyncio.wait_for(
            shop_agent.run(
                message,
                deps=ChatDependencies(
                    database_path=str(DATABASE),
                    shopper_name=(f"{user.first_name} {user.last_name}" if user else None),
                    shopper_email=(str(user.email) if user else None),
                    current_page=page,
                    current_product=current_product,
                ),
                message_history=history,
                model_settings={"timeout": 35.0},
                usage_limits=UsageLimits(request_limit=8, tool_calls_limit=8),
            ),
            timeout=75.0,
        )
        run_tool_calls = tool_calls_from(result)
    except TimeoutError as exc:
        write_audit_entry(new_entry(
            tool_calls=run_tool_calls,
            result={"status": "timed_out"},
            stop_reason="The 75-second agent-run deadline was reached.",
        ))
        raise HTTPException(
            status_code=504,
            detail="Shop chat timed out. Please try again.",
        ) from exc
    except Exception as exc:
        # Keep request content, credentials, provider responses, and exception text out of logs.
        limit_hit = type(exc).__name__ == "UsageLimitExceeded"
        write_audit_entry(new_entry(
            tool_calls=run_tool_calls,
            result={"status": "limit_reached" if limit_hit else "error"},
            stop_reason=(
                "The configured model-request or tool-call limit was reached."
                if limit_hit
                else "The agent, a tool, or the model provider returned an error. Details were omitted."
            ),
        ))
        raise HTTPException(status_code=502, detail="The shop chat could not get a response. Try again.") from exc

    write_audit_entry(new_entry(
        tool_calls=run_tool_calls,
        result={
            "status": "completed",
            "structured_reply_generated": bool(result.output.reply),
            "product_ids": result.output.product_ids[:8],
            "comparison_product_ids": result.output.comparison_product_ids[:2],
        },
        stop_reason="The agent returned validated structured output.",
    ))

    reply = result.output.reply
    constraints = chat_constraints(message, catalogue)
    requested_size, requested_color, max_price, exclusive_price, _ = constraints
    comparison_requested = bool(re.search(r"\b(compare|comparison|versus|vs)\b", message, re.I))
    comparison_ids = list(dict.fromkeys(
        product_id for product_id in result.output.comparison_product_ids
        if product_id in catalogue and satisfies_chat_constraints(catalogue[product_id], constraints)
    ))[:2]
    if comparison_requested and len(comparison_ids) < 2:
        comparison_ids = comparison_candidates(message, catalogue, constraints)
    products: list[ChatProductCard] = []
    included_ids: set[str] = set()
    requested_ids = [*result.output.product_ids, *comparison_ids]
    for product_id in requested_ids:
        if product_id in included_ids or product_id not in catalogue:
            continue
        product = catalogue[product_id]
        if not satisfies_chat_constraints(product, constraints):
            continue
        products.append(
            ChatProductCard(
                product_id=product.product_id,
                name=product.name,
                description=product.description,
                price=product.price,
                image_path=product.image_path,
            )
        )
        included_ids.add(product_id)
    constrained_discovery = bool(result.output.product_ids) and any(
        value is not None for value in (requested_size, requested_color, max_price)
    )
    if constrained_discovery:
        qualifiers = []
        if requested_size:
            qualifiers.append(f"{requested_size} in stock")
        if requested_color:
            qualifiers.append(f"in {requested_color}")
        if max_price is not None:
            qualifiers.append(
                f"priced under ${max_price:g}"
                if exclusive_price else f"priced at or below ${max_price:g}"
            )
        if products:
            reply = f"I found {len(products)} catalogue match{'es' if len(products) != 1 else ''} with {', '.join(qualifiers)}. The cards show products verified against current stock."
        else:
            reply = f"I couldn't find any matching products with {', '.join(qualifiers)} in stock."
    comparison: list[ProductComparisonItem] = []
    if comparison_requested and len(comparison_ids) == 2:
        comparison = [
            ProductComparisonItem(
                product_id=catalogue[product_id].product_id,
                name=catalogue[product_id].name,
                price=catalogue[product_id].price,
                colors=catalogue[product_id].colors,
                available_sizes=[stock.size for stock in catalogue[product_id].sizes if stock.in_stock],
            )
            for product_id in comparison_ids
        ]
        reply = "Here are two catalogue products to compare. The prices, colors, and available sizes below come from the database."
    if user is not None:
        with database() as connection:
            connection.execute(
                "INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)",
                (user.id, "user", message),
            )
            connection.execute(
                "INSERT INTO chat_messages (user_id, role, content, products_json) VALUES (?, ?, ?, ?)",
                (
                    user.id,
                    "assistant",
                    reply,
                    json.dumps(
                        {
                            "products": [p.model_dump() for p in products],
                            "comparison": [item.model_dump() for item in comparison],
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
    return ChatResponse(reply=reply, products=products, comparison=comparison)


@app.get("/api/chat/history", response_model=ChatHistoryResponse)
def chat_history(request: Request) -> ChatHistoryResponse:
    user = user_for_session(request)
    if user is None:
        return ChatHistoryResponse(messages=[])
    with database() as connection:
        rows = connection.execute(
            "SELECT role, content, products_json FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT 100",
            (user.id,),
        ).fetchall()
    catalogue = {p.product_id: p for p in load_catalogue(str(DATABASE))}
    messages: list[ChatHistoryMessage] = []
    for row in reversed(rows):
        cards: list[ChatProductCard] = []
        comparison: list[ProductComparisonItem] = []
        if row["role"] == "assistant" and row["products_json"]:
            try:
                saved = json.loads(row["products_json"])
                saved_products = saved if isinstance(saved, list) else saved.get("products", []) if isinstance(saved, dict) else []
                saved_comparison = saved.get("comparison", []) if isinstance(saved, dict) else []
                for item in saved_products:
                    product = catalogue.get(item.get("product_id")) if isinstance(item, dict) else None
                    if product:
                        cards.append(ChatProductCard(
                            product_id=product.product_id, name=product.name,
                            description=product.description, price=product.price,
                            image_path=product.image_path,
                        ))
                for item in saved_comparison:
                    product = catalogue.get(item.get("product_id")) if isinstance(item, dict) else None
                    if product:
                        comparison.append(ProductComparisonItem(
                            product_id=product.product_id,
                            name=product.name,
                            price=product.price,
                            colors=product.colors,
                            available_sizes=[stock.size for stock in product.sizes if stock.in_stock],
                        ))
            except (TypeError, json.JSONDecodeError):
                cards = []
                comparison = []
        if row["role"] in {"user", "assistant"}:
            messages.append(ChatHistoryMessage(role=row["role"], text=row["content"], products=cards, comparison=comparison))
    return ChatHistoryResponse(messages=messages)
