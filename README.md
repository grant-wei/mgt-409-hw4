# Campus Customs

A Yale apparel storefront built with React, Vite, TypeScript, FastAPI, SQLite, and PydanticAI. It includes catalogue search and filters, product pages, account login, saved chat for signed-in shoppers, and a shop assistant grounded in product and inventory data.

## Requirements

- Python 3.11 or newer
- Node.js 22.12 or newer
- The official HW4 data pack
- An OpenAI API key and model name for live chat

## Add the course data

Download the official HW4 `data.zip` and extract it into this project folder. The app expects:

```text
data/campus_customs.db
data/products/
```

The database and product images are local-only and are excluded from Git.

## Configure the chat model

Copy `.env.example` to `.env` in the project folder, then replace both placeholder values with your own model name and API key. The `.env` file is ignored by Git.

## Install dependencies

From the project folder, create the backend environment and install Python packages:

```powershell
py -3 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Install frontend packages:

```powershell
cd frontend
npm ci
cd ..
```

## Run the app

Start the backend in one terminal:

```powershell
cd backend
.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000
```

Start the frontend in a second terminal:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5174
```

Open `http://127.0.0.1:5174/`. The Vite development server forwards `/api` requests to the FastAPI server on port 8000.
