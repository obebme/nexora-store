from sqlalchemy import select

from nexora_backend.database import SessionLocal
from nexora_backend.models import Category, Product

# Фото с Unsplash. Использование разрешено лицензией Unsplash:
# https://unsplash.com/license
CATALOG = [
    {
        "category": "Обувь",
        "category_slug": "shoes",
        "sku": "NX-SHO-001",
        "name": "RIFT RUNNER 02",
        "slug": "rift-runner-02",
        "description": "Лёгкие кроссовки для городского темпа.",
        "price": "12990.00",
        "compare_at_price": "15990.00",
        "color_name": "Молочный / графит",
        "sizes": ["39", "40", "41", "42", "43", "44"],
        "stock_quantity": 40,
        "image_url": "/images/rift-runner.jpg",
    },
    {
        "category": "Одежда",
        "category_slug": "clothing",
        "sku": "NX-CLO-001",
        "name": "AFTERHOURS HOODIE",
        "slug": "afterhours-hoodie",
        "description": "Плотное худи свободного кроя.",
        "price": "8990.00",
        "compare_at_price": None,
        "color_name": "Выцветший чёрный",
        "sizes": ["S", "M", "L", "XL"],
        "stock_quantity": 35,
        "image_url": "/images/afterhours-hoodie.jpg",
    },
    {
        "category": "Одежда",
        "category_slug": "clothing",
        "sku": "NX-CLO-002",
        "name": "OFFGRID TRACK PANT",
        "slug": "offgrid-track-pant",
        "description": "Свободные брюки для движения каждый день.",
        "price": "7490.00",
        "compare_at_price": None,
        "color_name": "Угольный",
        "sizes": ["S", "M", "L", "XL"],
        "stock_quantity": 28,
        "image_url": "/images/offgrid-pants.jpg",
    },
    {
        "category": "Обувь",
        "category_slug": "shoes",
        "sku": "NX-SHO-002",
        "name": "STREET FORM 01",
        "slug": "street-form-01",
        "description": "Выразительная пара для городских маршрутов.",
        "price": "14990.00",
        "compare_at_price": None,
        "color_name": "Красный / белый",
        "sizes": ["39", "40", "41", "42", "43"],
        "stock_quantity": 22,
        "image_url": "/images/street-form.jpg",
    },
    {
        "category": "Одежда",
        "category_slug": "clothing",
        "sku": "NX-CLO-003",
        "name": "NO SIGNAL TEE",
        "slug": "no-signal-tee",
        "description": "Футболка свободной посадки из хлопка.",
        "price": "3990.00",
        "compare_at_price": "4990.00",
        "color_name": "Белый",
        "sizes": ["S", "M", "L", "XL"],
        "stock_quantity": 60,
        "image_url": "/images/no-signal-tee.jpg",
    },
    {
        "category": "Аксессуары",
        "category_slug": "accessories",
        "sku": "NX-ACC-001",
        "name": "UTILITY CROSSBODY",
        "slug": "utility-crossbody",
        "description": "Компактная сумка на каждый день.",
        "price": "5990.00",
        "compare_at_price": None,
        "color_name": "Чёрный",
        "sizes": ["ONE SIZE"],
        "stock_quantity": 30,
        "image_url": "/images/utility-crossbody.jpg",
    },
]


def main() -> None:
    with SessionLocal.begin() as db:
        categories: dict[str, Category] = {}
        for name, slug in [
            ("Обувь", "shoes"),
            ("Одежда", "clothing"),
            ("Аксессуары", "accessories"),
        ]:
            category = db.scalar(select(Category).where(Category.slug == slug))
            if category is None:
                category = Category(
                    name=name, slug=slug, description=f"Категория {name.lower()} NEXORA"
                )
                db.add(category)
                db.flush()
            categories[slug] = category
        for item in CATALOG:
            if db.scalar(select(Product.id).where(Product.sku == item["sku"])) is not None:
                continue
            product = {
                key: value
                for key, value in item.items()
                if key not in {"category", "category_slug"}
            }
            sizes = product["sizes"]
            total_stock = product["stock_quantity"]
            quotient, remainder = divmod(total_stock, len(sizes))
            product["stock_by_size"] = {
                size: quotient + (1 if index < remainder else 0) for index, size in enumerate(sizes)
            }
            db.add(Product(category_id=categories[item["category_slug"]].id, **product))


if __name__ == "__main__":
    main()
