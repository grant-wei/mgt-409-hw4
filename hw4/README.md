# Campus Customs

A Yale apparel storefront built with React, Vite, TypeScript, FastAPI, SQLite, and PydanticAI. It includes catalogue search and filters, product pages, account login, saved chat for signed-in shoppers, and a shop assistant grounded in product and inventory data.

## Requirements

- Python 3.11 or newer
- Node.js 22.12 or newer
- The official HW4 data pack
- An OpenAI API key and model name for live chat

## Add the course data

From the cloned repository root, enter the project folder:

```powershell
cd hw4
```

Download the official HW4 `data.zip` into this `hw4/` folder and extract it here:

```powershell
Expand-Archive -LiteralPath data.zip -DestinationPath .
```

The resulting paths, relative to the repository root, must be:

```text
hw4/data/campus_customs.db
hw4/data/products/
```

The database and product images are local-only and are excluded from Git.

## Configure the chat model

While inside `hw4/`, copy the configuration template:

```powershell
Copy-Item .env.example .env
```

Replace both placeholder values in `hw4/.env` with your own model name and API key. The `.env` file is ignored by Git. Existing process environment values take precedence. For an existing local setup, keep its configured `.env` instead of overwriting it.

## Install dependencies

From `hw4/`, create the backend environment and install Python packages:

```powershell
py -3 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Install frontend packages:

```powershell
cd frontend
npm.cmd ci
cd ..
```

## Run the app

Start the backend in a terminal opened at the repository root:

```powershell
cd hw4/backend
.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
```

Start the frontend in a second terminal opened at the repository root:

```powershell
cd hw4/frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5174
```

Open `http://127.0.0.1:5174/`. The Vite development server forwards `/api` requests to the FastAPI server on port 8000.

`npm.cmd run dev` and `npm.cmd run build` automatically prepare the catalogue JSON and product images from `hw4/data/`. Keep Python available as `python` on your PATH for that preparation step. The generated catalogue, copied product images, database, and real `.env` stay local and are ignored by Git.

## Build and check

From a terminal opened at the repository root:

```powershell
cd hw4/frontend
npm.cmd run build
npm.cmd run lint
```

The existing app-check screenshots are in `hw4/output/app_check_images/`. Open `hw4/output/app_check.html` to view them.
