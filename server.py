import os
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import List, Dict

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


create_table()


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


create_friend_requests_table()


class PlayerActions(BaseModel):
    name: str
    actions: List[Dict]  # Each action: {type, data, timestamp}


@app.post("/game/actions")
def receive_actions(payload: PlayerActions):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT score FROM leaderboard WHERE name = %s", (payload.name,))
    row = cursor.fetchone()
    score = row["score"] if row else 0

    for action in payload.actions:
        action_type = action["type"]
        if action_type == "click":
            score += 1
        elif action_type == "buy_upgrade":
            upgrade = action["data"].get("upgrade")
            if upgrade == "auto_spank":
                # placeholder for future sps/logic
                pass

    if row:
        cursor.execute("UPDATE leaderboard SET score = %s WHERE name = %s", (score, payload.name))
    else:
        cursor.execute("INSERT INTO leaderboard (name, score) VALUES (%s, %s)", (payload.name, score))

    conn.commit()
    cursor.close()
    conn.close()
    return {"message": "Actions processed"}


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
