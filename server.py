import os
from fastapi import FastAPI, HTTPException, Header, Request, Depends
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


class RegisterRequest(BaseModel):
    name: str

class PlayerActionsSecure(BaseModel):
    actions: List[Dict]

class PlayerTokenSecure(BaseModel):
    token: str

@app.post("/register", response_model=PlayerTokenSecure)
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

    return PlayerTokenSecure(token=token)

def get_authenticated_player(request: Request):
    token = request.headers.get("Authorization")
    if not token or not token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = token.split(" ")[1]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM players WHERE token = %s", (token,))
    player = cursor.fetchone()
    cursor.close()
    conn.close()

    if not player:
        raise HTTPException(status_code=401, detail="Invalid token")
    return player

@app.post("/game/actions")
def receive_actions(payload: PlayerActionsSecure, player=Depends(get_authenticated_player)):
    now = datetime.now(timezone.utc)
    last_updated = player["last_updated"]
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)

    sps = player["sps"]

    seconds_passed = (now - last_updated).total_seconds()
    passive_earned = int(sps * seconds_passed)

    click_count = sum(1 for a in payload.actions if a.get("type") == "click")

    max_clicks = int(seconds_passed * 15)
    if max_clicks < 1:
        max_clicks = 1

    if click_count > max_clicks:
        raise HTTPException(status_code=400, detail="Too many clicks in short time")

    score = player["score"] + passive_earned + click_count
    for action in payload.actions:
        if action["type"] == "buy_upgrade":
            upgrade = action["data"].get("upgrade")
            if upgrade == "auto_spank":
                price = (10 * 5.5) ** (sps + 1)
                if sps != 0:
                    price = price / (10 * sps)
                if score >= price:
                    score -= price
                    sps += 1
                else:
                    raise HTTPException(status_code=400, detail="Not enough spanks")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE players SET score = %s, sps = %s, last_updated = %s WHERE id = %s",
        (score, sps, now, player["id"])
    )
    conn.commit()
    cursor.close()
    conn.close()

    return {"message": f"Actions processed"}

@app.post("/game/updatesps")
def updatesps(payload: PlayerActionsSecure):
    token = payload.token
    if not token or not token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = token.split(" ")[1]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM players WHERE token = %s", (token,))
    player = cursor.fetchone()
    cursor.close()
    conn.close()

    if not player:
        raise HTTPException(status_code=401, detail="Invalid token")


    now = datetime.now(timezone.utc)
    last_updated = player["last_updated"]
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)

    sps = player["sps"]

    seconds_passed = (now - last_updated).total_seconds()
    passive_earned = int(sps * seconds_passed)

    score = player["score"] + passive_earned

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE players SET score = %s, sps = %s, last_updated = %s WHERE id = %s",
        (score, sps, now, player["id"])
    )
    conn.commit()
    cursor.close()
    conn.close()

    return {"message": f"Actions processed"}



@app.get("/player_data/{player_token}")
def get_player_data(player_token: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT score, sps FROM players WHERE token = %s", (player_token,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if row:
        return {"score": row["score"], "sps": row["sps"]}
    else:
        return {"score": 0, "sps": 0}

@app.post("/delete_player/{player_token}")
def delete_player(player_token: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM players WHERE token = %s", (player_token,))
    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "player deleted"}


@app.get("/token_valid")
def token_valid(request: Request):
    token = request.headers.get("Authorization")
    if not token or not token.startswith("Bearer "):
        return "false"

    token = token.split(" ")[1]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM players WHERE token = %s", (token,))
    player = cursor.fetchone()
    cursor.close()
    conn.close()

    if not player:
        return "false"
    return "true"

@app.get("/leaderboard")
def get_leaderboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, score FROM players ORDER BY score DESC LIMIT 10")
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
    cursor.execute("SELECT * FROM players WHERE name = %s", (friend,))
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
        SELECT players.name, players.score
        FROM friends
        JOIN players ON friends.friend_name = players.name
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
