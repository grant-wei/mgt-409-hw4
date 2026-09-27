from __future__ import annotations

import json
import sqlite3
from pathlib import Path, PurePosixPath

from pydantic_ai import Agent, RunContext

from models import AgentChatResult, ChatDependencies, ProductSummary, SizeStock


def load_catalogue(database_path: str) -> list[ProductSummary]:
    path = Path(database_path).resolve()
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        products = connection.execute(
            "SELECT product_id, name, garment_type, description, colors, search_tags, image_file_path, price FROM catalogue ORDER BY name"
        ).fetchall()
        stock_rows = connection.execute(
            "SELECT product_id, size, quantity FROM inventory ORDER BY product_id, size"
        ).fetchall()
    finally:
        connection.close()

    inventory: dict[str, list[SizeStock]] = {}
    for row in stock_rows:
        inventory.setdefault(row["product_id"], []).append(
            SizeStock(
                size=row["size"],
                quantity=row["quantity"],
                in_stock=row["quantity"] > 0,
            )
        )

    summaries: list[ProductSummary] = []
    for row in products:
        image_relative = PurePosixPath(str(row["image_file_path"]).replace("\\", "/"))
        try:
            colors = json.loads(row["colors"])
        except (TypeError, json.JSONDecodeError):
            colors = [part.strip() for part in (row["colors"] or "").split(",") if part.strip()]
        if not isinstance(colors, list):
            colors = [str(colors)]
        try:
            search_tags = json.loads(row["search_tags"])
        except (TypeError, json.JSONDecodeError):
            search_tags = [part.strip() for part in (row["search_tags"] or "").split(",") if part.strip()]
        if not isinstance(search_tags, list):
            search_tags = [str(search_tags)]
        summaries.append(
            ProductSummary(
                product_id=row["product_id"],
                name=row["name"],
                garment_type=row["garment_type"],
                description=row["description"],
                price=row["price"],
                image_path=f"/products/{image_relative.name}",
                colors=[str(color) for color in colors],
                search_tags=[str(tag) for tag in search_tags],
                sizes=inventory.get(row["product_id"], []),
            )
        )
    return summaries


def register_tools(agent: Agent[ChatDependencies, AgentChatResult]) -> None:
    @agent.tool
    async def search_products(
        ctx: RunContext[ChatDependencies], search_term: str, max_results: int = 5
    ) -> list[ProductSummary]:
        """Find shop products by name, garment type, description, or color."""
        term = search_term.strip().casefold()
        if not term:
            return []
        words: list[str] = []
        for word in term.split():
            if not word:
                continue
            words.append(word)
            if word.endswith("ies") and len(word) > 3:
                words.append(word[:-1])
            elif word.endswith("s") and len(word) > 3:
                words.append(word[:-1])
        matches: list[tuple[int, ProductSummary]] = []
        for product in load_catalogue(ctx.deps.database_path):
            searchable = " ".join(
                [product.product_id, product.name, product.garment_type, product.description, *product.colors, *product.search_tags]
            ).casefold()
            score = sum(2 if word in product.name.casefold() else 1 for word in words if word in searchable)
            if score:
                matches.append((score, product))
        matches.sort(key=lambda item: (-item[0], item[1].name.casefold()))
        return [product for _, product in matches[: max(1, min(max_results, 8))]]

    @agent.tool
    async def get_product_details(
        ctx: RunContext[ChatDependencies], product_id: str
    ) -> ProductSummary | None:
        """Look up one product and its size-level inventory by product ID."""
        target = product_id.strip()
        if not target:
            return None
        for product in load_catalogue(ctx.deps.database_path):
            if product.product_id == target:
                return product
        return None
