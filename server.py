import os
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict
from datetime import datetime, timezone
import uuid

app = FastAPI()

RESET_API_KEY = os.getenv("RESET_API_KEY")
if RESET_API_KEY is None:
    raise Exception("RESET_API_KEY is not set in the environment.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_db_connection():
    DATABASE_URL = os.getenv("DATABASE_URL")
    if DATABASE_URL is None:
        raise Exception("DATABASE_URL is not set in the environment.")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn


def create_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leaderboard (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            score INTEGER NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS friends (
            id SERIAL PRIMARY KEY,
            player_name TEXT NOT NULL,
            friend_name TEXT NOT NULL,
            UNIQUE(player_name, friend_name)
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()


def create_friend_requests_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS friend_requests (
            id SERIAL PRIMARY KEY,
            sender_name TEXT NOT NULL,
            receiver_name TEXT NOT NULL
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()


def create_players_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id UUID PRIMARY KEY,
            name TEXT,
            token TEXT UNIQUE NOT NULL,
            score INTEGER DEFAULT 0,
            sps INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT NOW()
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()


create_table()
create_friend_requests_table()
create_players_table()

def update_leaderboard_schema():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='leaderboard' AND column_name='sps';
    """)
    if cursor.fetchone() is None:
        cursor.execute("ALTER TABLE leaderboard ADD COLUMN sps INTEGER DEFAULT 0;")

    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='leaderboard' AND column_name='last_updated';
    """)
    if cursor.fetchone() is None:
        cursor.execute("ALTER TABLE leaderboard ADD COLUMN last_updated TIMESTAMP DEFAULT NOW();")

    conn.commit()
    cursor.close()
    conn.close()

update_leaderboard_schema()


class RegisterRequest(BaseModel):
    name: str

class RegisterResponse(BaseModel):
    player_id: str
    token: str

class PlayerActionsSecure(BaseModel):
    token: str
    actions: List[Dict]

@app.post("/register", response_model=RegisterResponse)
def register_player(payload: RegisterRequest):
    conn = get_db_connection()
    cursor = conn.cursor()

    player_id = str(uuid.uuid4())
    token = str(uuid.uuid4())

    cursor.execute("INSERT INTO players (id, name, token) VALUES (%s, %s, %s)",
                   (player_id, payload.name, token))
    conn.commit()
    cursor.close()
    conn.close()

    return RegisterResponse(player_id=player_id, token=token)

@app.post("/game/actions")
def receive_actions(payload: PlayerActionsSecure):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM players WHERE token = %s", (payload.token,))
    player = cursor.fetchone()

    if not player:
        raise HTTPException(status_code=401, detail="Invalid token")

    score = player["score"]
    sps = player["sps"]
    last_updated = player["last_updated"]

    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    seconds_passed = (now - last_updated).total_seconds()
    passive_earned = int(sps * seconds_passed)
    score += passive_earned

    for action in payload.actions:
        action_type = action["type"]
        if action_type == "click":
            score += 1
        elif action_type == "buy_upgrade":
            upgrade = action["data"].get("upgrade")
            if upgrade == "auto_spank":
                sps += 1

    cursor.execute(
        "UPDATE players SET score = %s, sps = %s, last_updated = %s WHERE id = %s",
        (score, sps, now, player["id"])
    )

    conn.commit()
    cursor.close()
    conn.close()

    return {"message": f"score:{score} ,Actions processed"}

@app.get("/player_data/{player_name}")
def get_player_data(player_name: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT score, sps FROM leaderboard WHERE name = %s", (player_name,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if row:
        return {"score": row["score"], "sps": row["sps"]}
    else:
        return {"score": 0, "sps": 0}

@app.get("/leaderboard")
def get_leaderboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, score FROM leaderboard ORDER BY score DESC LIMIT 10")
    leaderboard = cursor.fetchall()
    cursor.close()
    conn.close()
    return leaderboard


@app.post("/reset_leaderboard")
def reset_leaderboard(x_api_key: str = Header(None)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leaderboard")
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Leaderboard has been reset!"}


@app.post("/add_friend")
def add_friend(data: dict):
    player = data["player_name"]
    friend = data["friend_name"]

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leaderboard WHERE name = %s", (friend,))
    if not cursor.fetchone():
        conn.close()
        return {"message": "That player doesn't exist!"}

    cursor.execute("SELECT * FROM friends WHERE player_name = %s AND friend_name = %s", (player, friend))
    if cursor.fetchone():
        conn.close()
        return {"message": "Already friends!"}

    cursor.execute("SELECT * FROM friend_requests WHERE sender_name = %s AND receiver_name = %s", (player, friend))
    if cursor.fetchone():
        conn.close()
        return {"message": "Friend request already sent!"}

    cursor.execute("INSERT INTO friend_requests (sender_name, receiver_name) VALUES (%s, %s)", (player, friend))
    conn.commit()
    conn.close()
    return {"message": f"Friend request sent to {friend}!"}


@app.get("/friends/{player_name}")
def get_friends(player_name: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT leaderboard.name, leaderboard.score
        FROM friends
        JOIN leaderboard ON friends.friend_name = leaderboard.name
        WHERE friends.player_name = %s
    """, (player_name,))
    friends = cursor.fetchall()
    conn.close()
    return friends


@app.get("/get_friend_requests")
def get_friend_requests(username: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT sender_name FROM friend_requests WHERE receiver_name = %s", (username,))
    requests = [row["sender_name"] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return requests


@app.post("/respond_friend_request")
def respond_friend_request(data: dict):
    sender = data["sender"]
    receiver = data["receiver"]
    accept = data["accept"]

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM friend_requests WHERE sender_name = %s AND receiver_name = %s", (sender, receiver))

    if accept:
        cursor.execute("INSERT INTO friends (player_name, friend_name) VALUES (%s, %s)", (receiver, sender))
        cursor.execute("INSERT INTO friends (player_name, friend_name) VALUES (%s, %s)", (sender, receiver))

    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Friend request responded to!"}
