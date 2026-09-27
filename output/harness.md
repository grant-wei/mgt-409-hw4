# Harness

## Problem 2: Database tables

The live HW4 database contains four tables. Row counts below are from `data/campus_customs.db`.

### `catalogue` — 102 rows

The product catalogue powers search results, product cards, and detail pages.

| Field | Why it matters |
|---|---|
| `product_id` | Stable product key used to connect catalogue entries to stock rows. |
| `name` | Product name shown in search results and cards. |
| `garment_type` | Lets the shop classify and filter items such as hoodies and T-shirts. |
| `description` | Gives the chatbot and product detail page product-specific information. |
| `colors` | Color options help match customer requests to products. |
| `search_tags` | Search terms and synonyms help find products from natural language. |
| `image_file_path` | Locates the product image used in a card or detail page. |
| `price` | Displays the price and supports price-based comparisons. |

### `inventory` — 612 rows

Each row records stock for one product and size. `(product_id, size)` is unique, and `product_id` references `catalogue.product_id`.

| Field | Why it matters |
|---|---|
| `id` | Identifies an inventory row. |
| `product_id` | Connects the size and stock count to its catalogue product. |
| `size` | Identifies the product variant the shopper wants. |
| `quantity` | Shows whether that size is available and how many are in stock. |

### `users` — 3 rows

Account records connect customers to saved chat history.

| Field | Why it matters |
|---|---|
| `id` | Identifies an account and is referenced by `chat_messages.user_id`. |
| `name` | Stores the account's display name. |
| `email` | Uniquely identifies the account for sign-in and account lookup. |
| `password_hash` | Stores a password hash for authentication without storing the password itself. |
| `created_at` | Records when the account was created. |
| `first_name` | Stores the customer's first name separately for account display. |
| `last_name` | Stores the customer's last name separately for account display. |

### `chat_messages` — 22 rows

Each row stores one turn in a user's chat history. `user_id` references `users.id`.

| Field | Why it matters |
|---|---|
| `id` | Identifies a message and supports stable history ordering. |
| `user_id` | Connects the message to the account whose conversation it belongs to. |
| `role` | Distinguishes the customer turn from the assistant turn. |
| `content` | Stores the visible text of the chat turn. |
| `products_json` | Stores product-card data associated with a turn so displayed recommendations can be reconstructed. |
| `created_at` | Records when the message was saved and supports chronological history. |

## Source data

The project keeps the course database and product images under `data/`. The project `.gitignore` excludes both `/data/` and the downloaded `/data.zip` archive from Git.

## Problem 4: Authentication

The React account forms call the FastAPI backend through Vite's `/api` proxy. Run the backend from `backend/` with `.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000` while Vite is running.

- `POST /api/auth/register` validates first name, last name, email, and password, stores the normalized email and name fields in `users`, hashes the password, and starts a session.
- `POST /api/auth/login` checks the email and password. It returns the same generic error for an unknown email or a wrong password.
- `GET /api/auth/me` returns the current account from its session cookie.
- `POST /api/auth/logout` revokes that session and clears the cookie.

New passwords are stored as Argon2id hashes with a unique salt. The seeded users use a legacy PBKDF2-SHA256 hash, which is verified on login and upgraded to Argon2id after a successful match. Passwords are never stored in plaintext. The `password_hash` field is excluded from every response.

Sessions use random tokens in HttpOnly, SameSite=Lax cookies. SQLite stores only each token's SHA-256 digest in a `sessions` table, linked to the user with an expiry time. Set `AUTH_COOKIE_SECURE=true` when serving the app over HTTPS.


## Problem 5: Shop chatbot

Run the API from `backend/` with `.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000`. `agent.py` reads `OPENAI_API_KEY` and `OPENAI_MODEL` from the project root `.env` first, then checks the parent assignments `.env` for the existing local setup. Process environment values take precedence. The current model is `gpt-5`. The key stays in memory and is never returned or logged. The agent uses PydanticAI's OpenAI provider directly, with no Portkey gateway.

The frontend sends `{ "message": "..." }` to `POST /api/chat` through Vite's `/api` proxy. The route validates the message, supplies the SQLite path to the agent, and returns `{ "reply": "...", "products": [...] }`. When a valid session cookie is present, the route loads the last six user/assistant exchanges from `chat_messages` and saves the new turn pair. Anonymous chat is allowed and is not persisted.

`backend/tools.py` provides read-only catalogue search and product detail tools using the catalogue and inventory tables. `backend/models.py` defines the request, response, dependencies, and product data shapes. `backend/prompts/prompt.md` sets the Campus Customs voice and safety boundaries, including treating customer and product text as untrusted, protecting credentials, avoiding invented stock information, and staying within supported shop tasks. Provider errors return a generic response without logging the message or exception details.


## Problem 6: Product and stock tools

Both PydanticAI tools in `backend/tools.py` read the live SQLite catalogue and inventory using a read-only connection. They return a typed `ProductSummary` from `backend/models.py` so the agent can ground descriptions, prices, and stock statements in database fields.

### `search_products(search_term, max_results=5)`

Searches product IDs, names, garment types, descriptions, colors, and search tags. It returns matching products as `ProductSummary` records.

- `product_id` lets the agent fetch an exact canonical product after search.
- `name` and `garment_type` confirm which matching product the result represents.
- `description` supplies the actual product information shown to shoppers.
- `price` is the catalogue price and must be repeated as returned.
- `colors` and `search_tags` help match shopper wording to products.
- `sizes` lists database inventory records for that product. Each entry includes `size`, `quantity`, and `in_stock`. The quantity is the exact size-level count. `in_stock` is derived from that count and validated against it, so zero means out of stock.

### `get_product_details(product_id)`

Fetches one exact catalogue product by its database ID and returns the same `ProductSummary` fields. `product_id` binds the answer to the chosen row. `name` and `garment_type` verify that the ID matches the shopper's intended product. `description`, `price`, and `colors` give its canonical details. `sizes` gives the complete size-level inventory, with exact `quantity` and validated `in_stock` status for each size.

The prompt requires the agent to use a tool for product facts, to state exact counts, to clearly mark a zero count as out of stock, and to say when a requested size has no inventory row so its status cannot be verified. Missing sizes are not treated as zero. Tool outputs are catalogue facts, while any instructions embedded in customer or product text remain untrusted.


## Problem 7: Chat product cards

For category requests such as "hoodies", `backend/prompts/prompt.md` tells the PydanticAI agent to call `search_products` against the real catalogue and return up to eight matching database `product_id` values in the structured `AgentChatResult`. That result contains `reply` for the chat text and `product_ids` for selecting cards. For other requests, `product_ids` is empty.

`POST /api/chat` does not trust the model to author card details. It resolves each returned ID through `load_catalogue()` using `data/campus_customs.db`, drops IDs that do not exist, removes duplicates, and constructs the canonical `ChatProductCard` fields: `product_id` identifies the item, `name` and `description` provide its title and short info, `price` is the database price, and `image_path` maps the catalog image filename to the frontend's `/products/` asset route. These cards are returned in the `products` array alongside `reply`.

The React chat widget renders each `products` entry as an image, name, formatted price, and two-line description card. Its link uses `/products/{product_id}`, the same route as the Products grid, so selecting a chat match opens the existing full product detail page. Product assets and the Products page data are generated from the same SQLite catalogue by `frontend/scripts/prepare_data.py`. Authentication and the existing description, price, and per-size inventory flow continue through the same `/api/chat` route and session handling.

## Problem 8: Customer memory and page context

The existing `chat_messages` table already saved each authenticated shopper's user and assistant text. `/api/chat` continues writing those rows for the session's account only. Assistant rows also store returned product IDs in `products_json`, so recommendation cards can be restored with the conversation. Guests receive chat responses but their turns are not saved.

On chat-widget mount, the frontend calls `GET /api/chat/history`. The endpoint returns an empty history for guests and up to the signed-in account's latest 100 messages in chronological order. It scopes the query by the authenticated session's user ID. Stored product IDs are re-resolved against the current catalogue before cards are returned, preserving canonical names, descriptions, prices, and image paths. After login or account creation, the widget refreshes history as well. New chat requests continue to include the message and now send the current pathname.

The chat route validates that pathname as a local route, strips query and fragment values, and resolves `/products/{product_id}` to a `ProductSummary` from SQLite. `ChatDependencies` passes that page, optional product record, and the authenticated shopper's name and email to PydanticAI through dynamic instructions. Guest requests have no personal identity, while page and product context remain available. The prompt tells the agent to treat “this” as the current product when one is present, and verify product facts through the catalogue tools. Email stays private and should not be repeated unless directly relevant.

### Problem 8 followup: bounded waits and visible errors

The prior product-page request remained open because the installed OpenAI client defaults to a 600-second request timeout and the route did not set a total agent-run deadline. The API now gives each model request a 35-second timeout and caps the overall agent run at 75 seconds, returning an HTTP 504 timeout message when the overall cap is reached. The browser also aborts any chat fetch after 85 seconds and displays a chat error, with `finally` re-enabling the input and send button. Existing authenticated history writes and anonymous chat behavior remain on the same endpoints.

## Problem 12: Agent audit and run limits

`output/audit_trail.json` is a JSON array with one record appended for each actual PydanticAI agent run. Existing records are loaded and retained before a new record is written. Each record has a UTC `time`, `tool_name`, compact `args` including the run's tool calls and their sanitized arguments/results, a structured `result` summary, and a `stop_reason`. The log does not store raw shopper messages, provider errors, credentials, passwords, session values, shopper emails, or the full assistant reply. Search tool results include only compact product identity, price, and size stock fields. The audit writer serializes writes and replaces the file atomically after preserving all existing entries.

### `backend/models.py` fields and why they matter

- `ChatRequest.message` is the shopper's bounded request text. `current_page` lets the app provide page context without sending full URLs or query strings.
- `ChatProductCard.product_id` links to the canonical product page. `name`, `description`, `price`, and `image_path` supply the card content, with details resolved from the database by the route.
- `ProductComparisonItem.product_id` identifies each compared item. `name`, `price`, `colors`, and `available_sizes` let the app render a database-backed comparison. The response caps comparisons at two.
- `ChatResponse.reply` is the visible assistant response. `products` holds recommendation cards, and `comparison` holds comparison facts.
- `AgentChatResult.reply` is the agent's structured text. `product_ids` selects at most eight catalogue-backed cards, and `comparison_product_ids` selects at most two products for comparison.
- `SizeStock.size` identifies a variant. `quantity` is the database count and cannot be negative. `in_stock` is validated to equal `quantity > 0`.
- `ProductSummary.product_id` is the database key. `name` and `garment_type` identify the item. `description`, `price`, and `image_path` provide canonical product facts and the image location. `colors` and `search_tags` support matching. `sizes` supplies verified size-level stock.
- `ChatDependencies.database_path` points tools to the catalogue. `shopper_name` and `shopper_email` provide signed-in context when available, `current_page` provides route context, and `current_product` resolves “this” on product pages.
- `ChatHistoryMessage.role` distinguishes user and assistant turns. `text` contains displayed history, with `products` and `comparison` restoring associated cards and facts.
- `ChatHistoryResponse.messages` returns the ordered saved conversation.

### Tools, safety, bounds, model, and commands

`search_products(search_term, max_results)` searches catalogue name, ID, type, description, colors, and tags, and returns typed `ProductSummary` records with inventory. `max_results` is clamped to 1–8. `get_product_details(product_id)` fetches one exact product and its size-level inventory. Both read SQLite through a read-only connection. The prompt requires exact tool-backed price and stock answers, treats customer and product text as untrusted data, protects credentials and private account data, and limits the assistant to supported shopping help.

The PydanticAI run has an eight-request cap, an eight-tool-call cap, a 75-second total deadline, and a 35-second model-request timeout. Search results and card IDs are capped at eight. Comparisons are capped at two items. The configured model name is read from `OPENAI_MODEL` in the project root `.env`, then from the parent assignments `.env` for the existing local setup, or from the process environment. The API key is read into process memory and is never written to the audit trail. The current configured model is `gpt-5`.

Run the backend from `backend/`:

```powershell
.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

Run the frontend from `frontend/` in a separate terminal:

```powershell
npm run dev -- --host 127.0.0.1 --port 5174
```
