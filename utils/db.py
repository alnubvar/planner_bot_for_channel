import aiosqlite
from config import DB_PATH


# ============================
#       INIT DATABASE
# ============================


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                content TEXT NOT NULL,        -- текст или JSON
                channel_id TEXT NOT NULL,
                publish_time TEXT NOT NULL,   -- ISO-строка
                status TEXT DEFAULT 'pending' -- pending / sent
            )
            """
        )
        await db.commit()


# ============================
#         SAVE POST
# ============================


async def save_post(
    post_type: str, content: str, channel_id: str, publish_time: str
) -> int:
    """
    content — либо TEXT, либо JSON-строка.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO posts (type, content, channel_id, publish_time)
            VALUES (?, ?, ?, ?)
            """,
            (post_type, content, channel_id, publish_time),
        )
        await db.commit()

        cursor = await db.execute("SELECT last_insert_rowid()")
        row = await cursor.fetchone()
        return row[0]  # post_id


# ============================
#         GET POST
# ============================


async def get_scheduled_posts(post_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        row = await cursor.fetchone()

        return dict(row) if row else None


# ============================
#     GET ALL FUTURE POSTS
# ============================


async def get_all_pending_posts() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT * FROM posts
            WHERE status = 'pending'
            """
        )
        rows = await cursor.fetchall()

        return [dict(r) for r in rows]


# ============================
#         UPDATE POST
# ============================


async def update_post(
    post_id: int,
    new_content: str | None = None,
    new_type: str | None = None,
    new_publish_time: str | None = None,
):
    """
    Любые значения можно передавать как None — эти поля не изменятся.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        query = "UPDATE posts SET "
        params: list = []

        if new_content is not None:
            query += "content = ?, "
            params.append(new_content)

        if new_type is not None:
            query += "type = ?, "
            params.append(new_type)

        if new_publish_time is not None:
            query += "publish_time = ?, "
            params.append(new_publish_time)

        # убираем последний ", "
        query = query.rstrip(", ")

        query += " WHERE id = ?"
        params.append(post_id)

        await db.execute(query, params)
        await db.commit()


# ============================
#      MARK AS SENT
# ============================


async def mark_post_as_sent(post_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE posts SET status = 'sent' WHERE id = ?",
            (post_id,),
        )
        await db.commit()


# ============================
#         DELETE POST
# ============================


async def delete_post(post_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        await db.commit()


# ============================
#     PAGINATION (PENDING)
# ============================


async def get_pending_posts_page(limit: int, offset: int) -> list[dict]:
    """
    Возвращает страницу запланированных (pending) постов.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT *
            FROM posts
            WHERE status = 'pending'
            ORDER BY publish_time ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
