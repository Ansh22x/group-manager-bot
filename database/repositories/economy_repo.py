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
        """Gets user balance with FastCache (0ms memory lookup). chat_id is ignored to force a GLOBAL wallet."""
        from services.cache_service import fast_cache
        cached = fast_cache.get(f"wallet_{user_id}")
        if cached is not None:
            return cached

        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT balance FROM economy_wallets WHERE chat_id = 0 AND user_id = %s;", (user_id,))
                res = cur.fetchone()
                if not res:
                    cur.execute("INSERT INTO economy_wallets (chat_id, user_id, balance) VALUES (0, %s, 0) RETURNING balance;", (user_id,))
                    res = cur.fetchone()
                    conn.commit()
                bal = res[0] if res else 0
                fast_cache.set(f"wallet_{user_id}", bal, ttl_seconds=600.0)
                return bal
        except Exception:
            return 0
        finally:
            self.db.release_connection(conn)

    def add_coins(self, chat_id: int, user_id: int, amount: int) -> int:
        """Adds coins to the user's GLOBAL wallet with write-through caching."""
        from services.cache_service import fast_cache
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
                new_bal = res[0] if res else amount
                fast_cache.set(f"wallet_{user_id}", new_bal, ttl_seconds=600.0)
                return new_bal
        except Exception:
            conn.rollback()
            return 0
        finally:
            self.db.release_connection(conn)

    def deduct_coins(self, chat_id: int, user_id: int, amount: int) -> bool:
        """Deducts coins from the user's GLOBAL wallet with write-through caching."""
        from services.cache_service import fast_cache
        current = self.get_balance(chat_id, user_id)
        if current < amount: return False
        
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE economy_wallets SET balance = balance - %s WHERE chat_id = 0 AND user_id = %s RETURNING balance;", (amount, user_id))
                res = cur.fetchone()
                conn.commit()
                new_bal = res[0] if res else max(0, current - amount)
                fast_cache.set(f"wallet_{user_id}", new_bal, ttl_seconds=600.0)
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


class DailyStreakRepository(BaseRepository):
    def get_streak_info(self, user_id: int) -> dict:
        """Returns streak info: streak count, last_claimed datetime, can_claim boolean, and next_bonus."""
        import datetime
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT streak, last_claimed FROM daily_streaks WHERE user_id = %s;", (user_id,))
                r = cur.fetchone()
                if not r:
                    return {"streak": 0, "last_claimed": None, "can_claim": True, "reward": 100}
                
                streak, last_claimed = r[0], r[1]
                now = datetime.datetime.now(datetime.timezone.utc)
                if last_claimed.tzinfo is None:
                    last_claimed = last_claimed.replace(tzinfo=datetime.timezone.utc)
                
                diff = now - last_claimed
                # Can claim if 20 hours have passed
                can_claim = diff.total_seconds() >= 72000  # 20 hours
                
                # Check if streak broken (> 48 hours)
                if diff.total_seconds() > 172800:
                    current_streak = 0
                else:
                    current_streak = streak

                next_reward = min(100 + (current_streak * 50), 750)
                return {
                    "streak": current_streak,
                    "last_claimed": last_claimed,
                    "can_claim": can_claim,
                    "reward": next_reward,
                    "remaining_seconds": max(0, int(72000 - diff.total_seconds()))
                }
        except Exception as e:
            logger.error(f"Error in DailyStreakRepository.get_streak_info: {e}")
            return {"streak": 0, "last_claimed": None, "can_claim": True, "reward": 100}
        finally:
            self.db.release_connection(conn)

    def claim_daily(self, user_id: int) -> tuple[bool, int, int]:
        """Claims daily reward. Returns (success, new_streak, coins_awarded)."""
        info = self.get_streak_info(user_id)
        if not info["can_claim"]:
            return False, info["streak"], 0

        new_streak = info["streak"] + 1
        coins_awarded = min(100 + ((new_streak - 1) * 50), 750)

        conn = self.db.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO daily_streaks (user_id, streak, last_claimed)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id)
                    DO UPDATE SET streak = EXCLUDED.streak, last_claimed = CURRENT_TIMESTAMP;
                """, (user_id, new_streak))
                conn.commit()

            # Award coins to global wallet
            EconomyRepository().add_coins(0, user_id, coins_awarded)
            return True, new_streak, coins_awarded
        except Exception as e:
            conn.rollback()
            logger.error(f"Error in DailyStreakRepository.claim_daily: {e}")
            return False, 0, 0
        finally:
            self.db.release_connection(conn)
