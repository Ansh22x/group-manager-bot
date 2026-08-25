import logging
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

class EconomyRepository(BaseRepository):
    def get_bot_wallet_balance(self, bot_id: int = 0) -> int:
        """Retrieves or initializes the 100M coin Bot Treasury (Uses chat_id 0)"""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT balance FROM economy_wallets WHERE chat_id = 0 AND user_id = %s;", (bot_id,))
                res = cur.fetchone()
                if res: return res[0]
                
                initial_treasury = 100_000_000
                cur.execute("INSERT INTO economy_wallets (chat_id, user_id, balance) VALUES (0, %s, %s) RETURNING balance;", (bot_id, initial_treasury))
                conn.commit()
                return initial_treasury
        except Exception as e:
            logger.error(f"Error getting bot wallet: {e}")
            return 100_000_000
        finally:
            self.db.release_connection(conn)

    def modify_bot_wallet(self, amount: int, bot_id: int = 0) -> int:
        """Deducts or adds coins to the central Bot Treasury"""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE economy_wallets SET balance = balance + %s WHERE chat_id = 0 AND user_id = %s RETURNING balance;", (amount, bot_id))
                res = cur.fetchone()
                conn.commit()
                return res[0] if res else 0
        except Exception as e:
            conn.rollback()
            return 0
        finally:
            self.db.release_connection(conn)

    def get_balance(self, chat_id: int, user_id: int) -> int:
        """Gets user balance. chat_id is ignored to force a GLOBAL wallet."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT balance FROM economy_wallets WHERE chat_id = 0 AND user_id = %s;", (user_id,))
                res = cur.fetchone()
                if not res:
                    cur.execute("INSERT INTO economy_wallets (chat_id, user_id, balance) VALUES (0, %s, 0) RETURNING balance;", (user_id,))
                    res = cur.fetchone()
                    conn.commit()
                return res[0] if res else 0
        except Exception:
            return 0
        finally:
            self.db.release_connection(conn)

    def add_coins(self, chat_id: int, user_id: int, amount: int) -> int:
        """Adds coins to the user's GLOBAL wallet."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO economy_wallets (chat_id, user_id, balance) 
                    VALUES (0, %s, %s) 
                    ON CONFLICT (chat_id, user_id) 
                    DO UPDATE SET balance = economy_wallets.balance + EXCLUDED.balance 
                    RETURNING balance;
                """, (user_id, amount))
                res = cur.fetchone()
                conn.commit()
                return res[0] if res else amount
        except Exception:
            conn.rollback()
            return 0
        finally:
            self.db.release_connection(conn)

    def deduct_coins(self, chat_id: int, user_id: int, amount: int) -> bool:
        """Deducts coins from the user's GLOBAL wallet."""
        if self.get_balance(chat_id, user_id) < amount: return False
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE economy_wallets SET balance = balance - %s WHERE chat_id = 0 AND user_id = %s;", (amount, user_id))
                conn.commit()
                return True
        except Exception:
            conn.rollback()
            return False
        finally:
            self.db.release_connection(conn)


class ShopRepository(BaseRepository):
    def get_shop_items(self) -> list:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT item_id, name, cost, description FROM shop_items ORDER BY item_id ASC;")
                return [{"item_id": r[0], "name": r[1], "cost": r[2], "description": r[3]} for r in cur.fetchall()]
        except Exception:
            return []
        finally:
            self.db.release_connection(conn)

    def get_shop_item(self, item_id: int) -> dict:
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT item_id, name, cost, description FROM shop_items WHERE item_id = %s;", (item_id,))
                r = cur.fetchone()
                return {"item_id": r[0], "name": r[1], "cost": r[2], "description": r[3]} if r else {}
        except Exception:
            return {}
        finally:
            self.db.release_connection(conn)
