from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[1]
PROJECT = FRONTEND.parent
DATA = PROJECT / "data"
DATABASE = DATA / "campus_customs.db"
IMAGE_OUTPUT = FRONTEND / "public" / "products"
JSON_OUTPUT = FRONTEND / "src" / "data" / "products.json"


def main() -> None:
    if not DATABASE.is_file():
        raise FileNotFoundError(f"Course database not found: {DATABASE}")

    connection = sqlite3.connect(f"file:{DATABASE.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    products = connection.execute(
        """
        SELECT product_id, name, garment_type, description, colors, search_tags,
               image_file_path, price
        FROM catalogue
        ORDER BY name COLLATE NOCASE
        """
    ).fetchall()

    inventory_rows = connection.execute(
        "SELECT product_id, size, quantity FROM inventory ORDER BY product_id, size"
    ).fetchall()
    connection.close()

    inventory: dict[str, list[dict[str, object]]] = {}
    for row in inventory_rows:
        inventory.setdefault(row["product_id"], []).append(
            {"size": row["size"], "quantity": row["quantity"]}
        )

    IMAGE_OUTPUT.mkdir(parents=True, exist_ok=True)
    (FRONTEND / "src" / "data").mkdir(parents=True, exist_ok=True)
    exported: list[dict[str, object]] = []

    for row in products:
        relative_image = Path(row["image_file_path"].replace("\\", "/"))
        if relative_image.is_absolute() or ".." in relative_image.parts:
            raise ValueError(f"Invalid image path in catalogue: {row['image_file_path']}")
        if not relative_image.parts or relative_image.parts[0] != "products":
            raise ValueError(f"Unexpected image path in catalogue: {row['image_file_path']}")

        source_image = (DATA / relative_image).resolve()
        if DATA.resolve() not in source_image.parents or not source_image.is_file():
            raise FileNotFoundError(f"Product image not found: {source_image}")
        target_image = IMAGE_OUTPUT / relative_image.name
        shutil.copy2(source_image, target_image)

        exported.append(
            {
                "product_id": row["product_id"],
                "name": row["name"],
                "garment_type": row["garment_type"],
                "description": row["description"],
                "colors": json.loads(row["colors"]),
                "search_tags": json.loads(row["search_tags"]),
                "image_path": f"/products/{relative_image.name}",
                "price": row["price"],
                "inventory": inventory.get(row["product_id"], []),
            }
        )

    JSON_OUTPUT.write_text(json.dumps(exported, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(exported)} products and {len(list(IMAGE_OUTPUT.glob('*')))} images.")


if __name__ == "__main__":
    main()
