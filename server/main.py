import fastapi
import uvicorn
from pydantic import BaseModel, Field
from typing import List
from uuid import UUID, uuid4
from datetime import datetime
import sqlite3

app = fastapi.FastAPI()

DATABASE = 'test.db'


def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        phone_number TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        green_score REAL NOT NULL
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        cost REAL NOT NULL,
        carbon_emission REAL NOT NULL,
        sustainability_score REAL NOT NULL
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        product_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        impact_on_green_score REAL NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (product_id) REFERENCES products (id)
    )
    ''')

    conn.commit()
    conn.close()


def calculate_green_score(cost, carbon_emission):
    base_score = 100
    cost_factor = max(0, (50 - cost) / 50) * 20
    emission_factor = max(0, (20 - carbon_emission) / 20) * 80
    return int(base_score - cost_factor - emission_factor)


class User(BaseModel):
    phone_number: str = Field(..., pattern=r'^\d{10}$')
    name: str


class UserResponse(User):
    id: UUID
    green_score: float


class GreenScoreResponse(BaseModel):
    user_id: UUID
    green_score: float


class Product(BaseModel):
    name: str
    cost: float
    carbon_emission: float


class ProductResponse(Product):
    id: UUID
    sustainability_score: float


class Purchase(BaseModel):
    user_id: UUID
    product_id: UUID


class PurchaseResponse(BaseModel):
    id: int
    user_id: UUID
    product_id: UUID
    timestamp: datetime
    impact_on_green_score: float


class UserPurchaseResponse(BaseModel):
    id: int
    product_id: UUID
    product_name: str
    timestamp: datetime
    impact_on_green_score: float


@app.on_event("startup")
def on_startup():
    init_db()


@app.post("/users", response_model=UserResponse)
def register_user(user: User):
    user_id = uuid4()
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT id FROM users WHERE phone_number = ?
    ''', (user.phone_number,))
    existing_user = cursor.fetchone()

    if existing_user:
        conn.close()
        raise fastapi.HTTPException(status_code=400, detail="Phone number already registered")

    new_user = {
        "id": str(user_id),
        "phone_number": user.phone_number,
        "name": user.name,
        "green_score": 0.0
    }
    cursor.execute('''
    INSERT INTO users (id, phone_number, name, green_score)
    VALUES (?, ?, ?, ?)
    ''', (new_user["id"], new_user["phone_number"], new_user["name"], new_user["green_score"]))
    conn.commit()
    conn.close()
    return new_user


@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (str(user_id),))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise fastapi.HTTPException(status_code=404, detail="User not found")
    user = {"id": row[0], "phone_number": row[1], "name": row[2], "green_score": row[3]}
    return user


@app.get("/users/{user_id}/green-score", response_model=GreenScoreResponse)
async def get_green_score(user_id: UUID):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, green_score FROM users WHERE id = ?', (str(user_id),))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise fastapi.HTTPException(status_code=404, detail="User not found")
    return {"user_id": row[0], "green_score": row[1]}


@app.post("/purchases", response_model=PurchaseResponse)
def record_purchase(purchase: Purchase):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Check if user exists
    cursor.execute('SELECT * FROM users WHERE id = ?', (str(purchase.user_id),))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise fastapi.HTTPException(status_code=404, detail="User not found")

    # Check if product exists
    cursor.execute('SELECT * FROM products WHERE product_id = ?', (str(purchase.product_id),))
    product = cursor.fetchone()
    if not product:
        conn.close()
        raise fastapi.HTTPException(status_code=404, detail="Product not found")
    impact_on_green_score = product[4]  # Assuming sustainability_score is the 5th column
    new_green_score = user[3] + impact_on_green_score

    # Update user's green score
    cursor.execute('UPDATE users SET green_score = ? WHERE id = ?', (new_green_score, str(purchase.user_id)))

    timestamp = datetime.utcnow().isoformat()
    cursor.execute('''
    INSERT INTO purchases (user_id, product_id, timestamp, impact_on_green_score)
    VALUES (?, ?, ?, ?)
    ''', (str(purchase.user_id), str(purchase.product_id), timestamp, impact_on_green_score))
    purchase_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {"id": purchase_id, "user_id": purchase.user_id, "product_id": purchase.product_id, "timestamp": timestamp,
            "impact_on_green_score": impact_on_green_score}


@app.get("/users/{user_id}/purchases", response_model=List[UserPurchaseResponse])
async def get_user_purchases(user_id: UUID):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute('SELECT * FROM users WHERE id = ?', (str(user_id),))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Fetch purchases and their corresponding product names
        cursor.execute("""
            SELECT p.id, p.product_id, pr.name AS product_name, p.timestamp, p.impact_on_green_score
            FROM purchases p
            JOIN products pr ON p.product_id = pr.id
            WHERE p.user_id = ?
        """, (str(user_id),))
        purchases = cursor.fetchall()
        
        user_purchases = [
            UserPurchaseResponse(
                id=purchase['id'],
                product_id=purchase['product_id'],
                product_name=purchase['product_name'],
                timestamp=purchase['timestamp'],
                impact_on_green_score=purchase['impact_on_green_score']
            ) for purchase in purchases
        ]
    finally:
        conn.close()

    return user_purchases
    conn.close()
    return user_purchases


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
