# -*- coding: utf-8 -*-
from demoparser2 import DemoParser
import pandas as pd
from collections import defaultdict
from typing import Dict, Any, Optional, List


class CS2DemoAnalyzer:
    KNIFE_KEYWORDS = (
        "knife", "bayonet", "karambit", "dagger", "falchion",
        "butterfly", "m9", "tactical", "kukri", "ursus",
        "stiletto", "navaja", "skeleton", "survival", "paracord",
        "nomad", "classic"
    )

    ECO_WEAPONS_PREFIX = (
        "glock", "hkp2000", "usp", "p250", "cz75", "fiveseven", "tec9", "deagle", "revolver",
        "mp9", "mac10", "mp7", "mp5", "ump", "p90", "bizon",
        "nova", "xm1014", "mag7", "sawedoff",
        "zeus"
    )

    BOMB_EVENT_NAMES = (
        "bomb_planted",
        "bomb_defused",
        "bomb_exploded",
        "bomb_explode",
    )

    def __init__(self, demo_path: str, *, verbose: bool = False):
        self.demo_path = demo_path
        self.verbose = verbose
        self.parser = DemoParser(demo_path)

        self.players = defaultdict(lambda: {
            "nickname": "",
            "steamid": "",
            "team": "",
            "kills": 0,
            "deaths": 0,
            "assists": 0,
            "damage": 0.0,
            "headshots": 0,
            "rounds_played": 0,
            "first_kills": 0,
            "first_deaths": 0,
        })

        self._round_damage_by_attacker = defaultdict(lambda: defaultdict(float))
        self._weapon_stats = defaultdict(lambda: defaultdict(lambda: {"kills": 0, "headshots": 0, "damage": 0}))

        self.total_rounds = 0
        self.ct_score = 0
        self.t_score = 0
        self.round_winners = []  # "CT"/"T"

        # round events saved for backend rating
        self.round_events: List[Dict[str, Any]] = []

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    @staticmethod
    def _norm_str(x: Optional[Any]) -> str:
        if x is None:
            return ""
        s = str(x).strip()
        if s.lower() in ("nan", "none"):
            return ""
        return s

    @staticmethod
    def _norm_team(x: Optional[Any]) -> str:
        if x is None:
            return ""
        s = str(x).strip()
        if s.lower() in ("nan", "none"):
            return ""
        return s

    def _is_knife_weapon(self, weapon: Any) -> bool:
        if weapon is None:
            return False
        w = str(weapon).strip().lower()
        if not w or w in ("none", "nan"):
            return False
        return any(k in w for k in self.KNIFE_KEYWORDS)

    def _weapon_is_eco_proxy(self, weapon: str) -> bool:
        w = (weapon or "").strip().lower()
        if not w or w in ("none", "nan"):
            return False
        if self._is_knife_weapon(w):
            return True
        return any(w.startswith(p) for p in self.ECO_WEAPONS_PREFIX)

    def _teamname_to_side(self, team_name: str) -> Optional[str]:
        t = (team_name or "").strip().upper()
        if not t:
            return None
        if "CT" in t or "COUNTER" in t:
            return "CT"
        if t == "T" or "TERROR" in t or "TERRORIST" in t:
            return "T"
        if "TERROR" in t:
            return "T"
        if " T" in f" {t} ":
            return "T"
        return None

    def _ensure_player(self, steamid: str, row, role: str):
        p = self.players[steamid]
        if not p["steamid"]:
            p["steamid"] = str(steamid)

        if role == "victim":
            name = row.get("user_name") or row.get("name")
            team = row.get("user_team_name") or row.get("team_name")
        elif role == "attacker":
            name = row.get("attacker_name")
            team = row.get("attacker_team_name")
        else:
            name = row.get("assister_name")
            team = row.get("assister_team_name")

        if name and not p["nickname"]:
            p["nickname"] = str(name)

        if team and not p["team"]:
            p["team"] = str(team)

    def _player_side(self, steamid: str, row, role: str) -> Optional[str]:
        if not steamid:
            return None

        sid = str(steamid)
        known_team = self._norm_team(self.players.get(sid, {}).get("team"))
        side = self._teamname_to_side(known_team)
        if side:
            return side

        if role == "victim":
            team = self._norm_team(row.get("user_team_name") or row.get("team_name"))
        elif role == "attacker":
            team = self._norm_team(row.get("attacker_team_name"))
        else:
            team = self._norm_team(row.get("assister_team_name"))

        return self._teamname_to_side(team)

    def _is_teammate(self, attacker: str, victim: str, row) -> bool:
        at = self._norm_team(self.players.get(attacker, {}).get("team"))
        vt = self._norm_team(self.players.get(victim, {}).get("team"))
        if at and vt:
            return at == vt

        at2 = self._norm_team(row.get("attacker_team_name"))
        vt2 = self._norm_team(row.get("user_team_name") or row.get("team_name"))
        if at2 and vt2:
            return at2 == vt2

        return False

    @staticmethod
    def _winner_to_side(winner_raw: Any) -> Optional[str]:
        if winner_raw is None:
            return None

        if isinstance(winner_raw, (int,)):
            if winner_raw == 3:
                return "CT"
            if winner_raw == 2:
                return "T"
            return None

        s = str(winner_raw).strip()
        if not s or s.lower() in ("nan", "none"):
            return None

        if s.isdigit():
            v = int(s)
            if v == 3:
                return "CT"
            if v == 2:
                return "T"
            return None

        u = s.upper()
        if "CT" in u:
            return "CT"
        if u == "T" or "TERROR" in u:
            return "T"

        return None

    def _push_event(
        self,
        event_type: str,
        round_number: int,
        tick: Any,
        attacker_id: Optional[str],
        victim_id: Optional[str],
        weapon: str,
        headshot: bool,
        damage: float,
        alive_t_before: int,
        alive_ct_before: int,
        eco_t: bool,
        eco_ct: bool,
        score_t_before_round: int,
        score_ct_before_round: int,
        planter_id: Optional[str] = None,
        defuser_id: Optional[str] = None,
        bombsite: Optional[str] = None,
        has_defuse_kit: bool = False,
        time_in_round: Optional[float] = None,
        # ✅ NEW: side fields (HLTV Swing critical)
        attacker_side: Optional[str] = None,
        victim_side: Optional[str] = None,
        # round_result fields
        winner_side: Optional[str] = None,
        win_reason: Optional[str] = None,
        bomb_planted: Optional[bool] = None,
    ):
        try:
            tick_i = int(tick) if tick is not None and str(tick).strip().isdigit() else None
        except Exception:
            tick_i = None

        self.round_events.append({
            "event_type": event_type,
            "round_number": int(round_number),
            "tick": tick_i,

            "attacker_id": str(attacker_id) if attacker_id else None,
            "victim_id": str(victim_id) if victim_id else None,

            # ✅ NEW: persist sides into events
            "attacker_side": (str(attacker_side).strip().upper() if attacker_side else None),
            "victim_side": (str(victim_side).strip().upper() if victim_side else None),

            "weapon": (weapon or "").strip().lower(),
            "headshot": bool(headshot),
            "damage": float(damage) if damage is not None else 0.0,

            "alive_t": int(alive_t_before),
            "alive_ct": int(alive_ct_before),

            "eco_t": bool(eco_t),
            "eco_ct": bool(eco_ct),

            "score_t": int(score_t_before_round),
            "score_ct": int(score_ct_before_round),

            "planter_id": str(planter_id) if planter_id else None,
            "defuser_id": str(defuser_id) if defuser_id else None,
            "bombsite": (str(bombsite).strip().upper() if bombsite else None),
            "has_defuse_kit": bool(has_defuse_kit),
            "time_in_round": float(time_in_round) if time_in_round is not None else None,

            "winner_side": (str(winner_side).strip().upper() if winner_side else None),
            "win_reason": (str(win_reason).strip() if win_reason else None),
            "bomb_planted": bool(bomb_planted) if bomb_planted is not None else None,
        })

    def _extract_bombsite(self, row) -> Optional[str]:
        for k in ("site", "bombsite", "bomb_site", "plant_site", "site_name"):
            v = row.get(k)
            if v is not None and str(v).strip() and str(v).lower() not in ("nan", "none"):
                s = str(v).strip().upper()
                if s == "A" or s.endswith("A"):
                    return "A"
                if s == "B" or s.endswith("B"):
                    return "B"
                return s
        return None

    def _extract_has_kit(self, row) -> bool:
        for k in ("has_defuse_kit", "hasKit", "has_kit", "defuser_has_kit", "kit"):
            v = row.get(k)
            if v is None:
                continue
            s = str(v).strip().lower()
            if s in ("1", "true", "yes"):
                return True
            if s in ("0", "false", "no"):
                return False
            if isinstance(v, (int, float)) and v > 0:
                return True
        return False

    def _apply_bomb_event(
        self,
        row,
        *,
        round_number: int,
        alive_state: Dict[str, int],
        score_t_before_round: int,
        score_ct_before_round: int,
        bomb_state: Dict[str, bool],
    ):
        ev = row.get("event_name")
        tick = row.get("tick")

        alive_t_before = alive_state.get("T", 5)
        alive_ct_before = alive_state.get("CT", 5)

        eco_t = False
        eco_ct = False

        actor = row.get("user_steamid") or row.get("steamid")
        if actor is not None:
            actor = str(actor)

        bombsite = self._extract_bombsite(row)
        has_kit = self._extract_has_kit(row)

        time_in_round = None
        for k in ("time_in_round", "time", "seconds", "round_time"):
            v = row.get(k)
            if v is None:
                continue
            try:
                time_in_round = float(v)
                break
            except Exception:
                pass

        if ev == "bomb_planted":
            bomb_state["planted"] = True
            self._push_event(
                event_type="bomb_planted",
                round_number=round_number,
                tick=tick,
                attacker_id=None,
                victim_id=None,
                weapon="",
                headshot=False,
                damage=0.0,
                alive_t_before=alive_t_before,
                alive_ct_before=alive_ct_before,
                eco_t=eco_t,
                eco_ct=eco_ct,
                score_t_before_round=score_t_before_round,
                score_ct_before_round=score_ct_before_round,
                planter_id=actor,
                bombsite=bombsite,
                has_defuse_kit=False,
                time_in_round=time_in_round,
            )

        elif ev == "bomb_defused":
            bomb_state["planted"] = False
            self._push_event(
                event_type="bomb_defused",
                round_number=round_number,
                tick=tick,
                attacker_id=None,
                victim_id=None,
                weapon="",
                headshot=False,
                damage=0.0,
                alive_t_before=alive_t_before,
                alive_ct_before=alive_ct_before,
                eco_t=eco_t,
                eco_ct=eco_ct,
                score_t_before_round=score_t_before_round,
                score_ct_before_round=score_ct_before_round,
                defuser_id=actor,
                bombsite=bombsite,
                has_defuse_kit=has_kit,
                time_in_round=time_in_round,
            )

        elif ev in ("bomb_exploded", "bomb_explode"):
            bomb_state["planted"] = False
            self._push_event(
                event_type="bomb_exploded",
                round_number=round_number,
                tick=tick,
                attacker_id=None,
                victim_id=None,
                weapon="",
                headshot=False,
                damage=0.0,
                alive_t_before=alive_t_before,
                alive_ct_before=alive_ct_before,
                eco_t=eco_t,
                eco_ct=eco_ct,
                score_t_before_round=score_t_before_round,
                score_ct_before_round=score_ct_before_round,
                bombsite=bombsite,
                time_in_round=time_in_round,
            )

    def _apply_death(
        self,
        row,
        first_kill_done: bool,
        *,
        round_number: int,
        alive_state: Dict[str, int],
        score_t_before_round: int,
        score_ct_before_round: int,
    ) -> bool:
        victim = row.get("user_steamid") or row.get("steamid")
        attacker = row.get("attacker_steamid")
        assister = row.get("assister_steamid")
        headshot = row.get("headshot", False)
        weapon = self._norm_str(row.get("weapon")).lower()
        tick = row.get("tick")

        if not victim:
            return first_kill_done

        victim = str(victim)
        self._ensure_player(victim, row, "victim")
        self.players[victim]["deaths"] += 1

        victim_side = self._player_side(victim, row, "victim")

        if attacker and str(attacker) != "0":
            attacker = str(attacker)

            if attacker != victim:
                self._ensure_player(attacker, row, "attacker")

                if not self._is_teammate(attacker, victim, row):
                    self.players[attacker]["kills"] += 1

                    if bool(headshot):
                        self.players[attacker]["headshots"] += 1

                    if weapon:
                        ws = self._weapon_stats[attacker][weapon]
                        ws["kills"] += 1
                        if bool(headshot):
                            ws["headshots"] += 1

                    if not first_kill_done:
                        self.players[attacker]["first_kills"] += 1
                        self.players[victim]["first_deaths"] += 1
                        first_kill_done = True

                    attacker_side = self._player_side(attacker, row, "attacker")

                    alive_t_before = alive_state.get("T", 5)
                    alive_ct_before = alive_state.get("CT", 5)

                    eco_proxy = self._weapon_is_eco_proxy(weapon)
                    eco_t = eco_proxy if attacker_side == "T" else False
                    eco_ct = eco_proxy if attacker_side == "CT" else False

                    self._push_event(
                        event_type="kill",
                        round_number=round_number,
                        tick=tick,
                        attacker_id=attacker,
                        victim_id=victim,
                        weapon=weapon,
                        headshot=bool(headshot),
                        damage=100.0,
                        alive_t_before=alive_t_before,
                        alive_ct_before=alive_ct_before,
                        eco_t=eco_t,
                        eco_ct=eco_ct,
                        score_t_before_round=score_t_before_round,
                        score_ct_before_round=score_ct_before_round,
                        # ✅ NEW: persist sides
                        attacker_side=attacker_side,
                        victim_side=victim_side,
                    )

                    if victim_side in ("T", "CT"):
                        alive_state[victim_side] = max(0, alive_state.get(victim_side, 5) - 1)

        if assister and str(assister) != "0":
            assister = str(assister)
            if assister not in (victim, str(attacker) if attacker else None):
                self._ensure_player(assister, row, "assister")
                self.players[assister]["assists"] += 1
                
                # ✅ CRITICAL FIX: Push assist event for KAST calculation!
                assister_side = self._player_side(assister, row, "assister")
                
                alive_t_before = alive_state.get("T", 5)
                alive_ct_before = alive_state.get("CT", 5)
                
                # Use same eco values as the kill event
                eco_t = eco_t if 'eco_t' in locals() else False
                eco_ct = eco_ct if 'eco_ct' in locals() else False
                
                self._push_event(
                    event_type="assist",
                    round_number=round_number,
                    tick=tick,
                    attacker_id=assister,
                    victim_id=victim,
                    weapon=weapon,
                    headshot=False,
                    damage=0.0,
                    alive_t_before=alive_t_before,
                    alive_ct_before=alive_ct_before,
                    eco_t=eco_t,
                    eco_ct=eco_ct,
                    score_t_before_round=score_t_before_round,
                    score_ct_before_round=score_ct_before_round,
                    attacker_side=assister_side,
                    victim_side=victim_side,
                )

        return first_kill_done

    def _apply_damage(
        self,
        row,
        *,
        round_number: int,
        alive_state: Dict[str, int],
        score_t_before_round: int,
        score_ct_before_round: int,
    ):
        victim = row.get("user_steamid") or row.get("steamid")
        attacker = row.get("attacker_steamid")
        damage = row.get("dmg_health", 0)
        weapon = self._norm_str(row.get("weapon")).lower()
        tick = row.get("tick")

        if not attacker or not victim:
            return

        attacker = str(attacker)
        victim = str(victim)

        if attacker == "0" or attacker == victim:
            return

        try:
            dmg = float(damage)
        except Exception:
            return

        if dmg <= 0:
            return

        self._ensure_player(attacker, row, "attacker")
        self._ensure_player(victim, row, "victim")

        if self._is_teammate(attacker, victim, row):
            return

        current = self._round_damage_by_attacker[attacker][victim]
        allowed = 100.0 - current
        if allowed <= 0:
            return

        real = dmg if dmg <= allowed else allowed
        self._round_damage_by_attacker[attacker][victim] = current + real

        if weapon:
            self._weapon_stats[attacker][weapon]["damage"] += int(round(real))

        attacker_side = self._player_side(attacker, row, "attacker")
        victim_side = self._player_side(victim, row, "victim")

        alive_t_before = alive_state.get("T", 5)
        alive_ct_before = alive_state.get("CT", 5)

        eco_proxy = self._weapon_is_eco_proxy(weapon)
        eco_t = eco_proxy if attacker_side == "T" else False
        eco_ct = eco_proxy if attacker_side == "CT" else False

        self._push_event(
            event_type="damage",
            round_number=round_number,
            tick=tick,
            attacker_id=attacker,
            victim_id=victim,
            weapon=weapon,
            headshot=False,
            damage=float(real),
            alive_t_before=alive_t_before,
            alive_ct_before=alive_ct_before,
            eco_t=eco_t,
            eco_ct=eco_ct,
            score_t_before_round=score_t_before_round,
            score_ct_before_round=score_ct_before_round,
            # ✅ NEW: persist sides
            attacker_side=attacker_side,
            victim_side=victim_side,
        )

    def _finalize_round_damage(self):
        for attacker in self._round_damage_by_attacker:
            total = sum(self._round_damage_by_attacker[attacker].values())
            self.players[attacker]["damage"] += total

        self._round_damage_by_attacker = defaultdict(lambda: defaultdict(float))

    def parse(self) -> Dict[str, Any]:
        try:
            header = self.parser.parse_header()
            map_name = header.get("map_name", "Unknown")

            events = ["player_death", "player_hurt", "round_end", "round_announce_match_start"]
            events += list(self.BOMB_EVENT_NAMES)

            dfs = []
            for event in events:
                try:
                    df = self.parser.parse_event(
                        event,
                        player=[
                            "steamid", "name", "team_name",
                            "user_steamid", "user_name", "user_team_name",
                            "tick"
                        ],
                        other=[
                            "attacker_steamid", "attacker_name", "attacker_team_name",
                            "assister_steamid", "assister_name", "assister_team_name",
                            "weapon", "headshot", "dmg_health", "winner", "tick",
                            "site", "bombsite", "has_defuse_kit", "has_kit", "kit",
                            "time_in_round", "time", "seconds",
                            "reason", "win_reason"
                        ],
                    )
                except Exception:
                    df = None

                if isinstance(df, pd.DataFrame) and (not df.empty):
                    df["event_name"] = event
                    dfs.append(df)

            if not dfs:
                return self._error("No events found")

            df = pd.concat(dfs, ignore_index=True)

            if "tick" in df.columns:
                df["_tick_sort"] = pd.to_numeric(df["tick"], errors="coerce")
                df = df.sort_values(by=["_tick_sort"], kind="mergesort").drop(columns=["_tick_sort"])

            self._process_rounds_v2(df)
            return self._build_result(map_name)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._error(str(e))

    def _process_rounds_v2(self, df: pd.DataFrame):
        print("PROCESS ROUNDS CALLED")

        all_rounds = []
        buffer_events = []
        announce_ticks = []

        for _, row in df.iterrows():
            ev = row.get("event_name")

            if ev == "round_announce_match_start":
                tick = row.get("tick")
                announce_ticks.append(tick)
                continue

            if ev in ("player_death", "player_hurt") or ev in self.BOMB_EVENT_NAMES:
                buffer_events.append(row)
                continue

            if ev == "round_end":
                winner_side = self._winner_to_side(self._norm_str(row.get("winner")))
                if winner_side:
                    death_weapons = [
                        self._norm_str(r.get("weapon")).lower()
                        for r in buffer_events
                        if r.get("event_name") == "player_death"
                    ]

                    is_knife_only = (len(death_weapons) > 0) and all(self._is_knife_weapon(w) for w in death_weapons)
                    has_deaths = len(death_weapons) > 0
                    reason = self._norm_str(row.get("reason") or row.get("win_reason"))

                    all_rounds.append({
                        "winner": winner_side,
                        "reason": reason,
                        "is_knife_only": is_knife_only,
                        "has_deaths": has_deaths,
                        "events": buffer_events.copy(),
                        "tick": row.get("tick"),
                    })

                buffer_events = []

        match_start_idx = 0

        if announce_ticks:
            last_announce_tick = announce_ticks[-1]
            for i, r in enumerate(all_rounds):
                if r["tick"] and r["tick"] > last_announce_tick:
                    if r["is_knife_only"]:
                        match_start_idx = i + 1
                    else:
                        match_start_idx = i
                    break

        if match_start_idx == 0:
            for i, r in enumerate(all_rounds):
                if r["is_knife_only"]:
                    match_start_idx = i + 1
                    break

        if match_start_idx == 0:
            for i in range(1, min(5, len(all_rounds))):
                if i < len(all_rounds) - 1:
                    if all_rounds[i]["winner"] != all_rounds[i - 1]["winner"]:
                        match_start_idx = i
                        break

        for i in range(match_start_idx, len(all_rounds)):
            round_data = all_rounds[i]
            self.total_rounds += 1
            round_number = self.total_rounds

            score_ct_before_round = self.ct_score
            score_t_before_round = self.t_score

            winner = round_data["winner"]
            if winner == "CT":
                self.ct_score += 1
            else:
                self.t_score += 1

            self.round_winners.append(winner)

            alive_state = {"T": 5, "CT": 5}
            bomb_state = {"planted": False}
            first_kill_done = False

            for r in round_data["events"]:
                ev = r.get("event_name")

                if ev == "player_death":
                    first_kill_done = self._apply_death(
                        r, first_kill_done,
                        round_number=round_number,
                        alive_state=alive_state,
                        score_t_before_round=score_t_before_round,
                        score_ct_before_round=score_ct_before_round
                    )

                elif ev == "player_hurt":
                    self._apply_damage(
                        r,
                        round_number=round_number,
                        alive_state=alive_state,
                        score_t_before_round=score_t_before_round,
                        score_ct_before_round=score_ct_before_round
                    )

                elif ev in self.BOMB_EVENT_NAMES:
                    self._apply_bomb_event(
                        r,
                        round_number=round_number,
                        alive_state=alive_state,
                        score_t_before_round=score_t_before_round,
                        score_ct_before_round=score_ct_before_round,
                        bomb_state=bomb_state
                    )

            self._finalize_round_damage()

            self._push_event(
                event_type="round_result",
                round_number=round_number,
                tick=round_data.get("tick"),
                attacker_id=None,
                victim_id=None,
                weapon="",
                headshot=False,
                damage=0.0,
                alive_t_before=int(alive_state.get("T", 0)),
                alive_ct_before=int(alive_state.get("CT", 0)),
                eco_t=False,
                eco_ct=False,
                score_t_before_round=score_t_before_round,
                score_ct_before_round=score_ct_before_round,
                winner_side=winner,
                win_reason=(round_data.get("reason") or None),
                bomb_planted=bool(bomb_state.get("planted", False)),
            )

        for sid in self.players:
            self.players[sid]["rounds_played"] = self.total_rounds

    def _build_result(self, map_name: str) -> Dict[str, Any]:
        players_list = []

        for sid, data in self.players.items():
            rounds = data["rounds_played"]
            if rounds <= 0:
                continue

            sid_str = str(sid).strip().lower() if sid is not None else ""
            if not sid_str or sid_str in ("nan", "none", "0"):
                continue

            nickname_clean = str(data.get("nickname") or "").strip()
            if not nickname_clean or nickname_clean.lower() in ("nan", "none", "undefined"):
                continue

            steamid_clean = str(data.get("steamid") or "").strip()
            if not steamid_clean or steamid_clean.lower() in ("nan", "none", "0"):
                continue

            kills = data["kills"]
            deaths = data["deaths"]

            adr = round((data["damage"] / rounds), 1) if rounds > 0 else 0.0
            kd = round(kills / deaths, 2) if deaths > 0 else kills
            hs = round((data["headshots"] / kills * 100), 1) if kills > 0 else 0.0

            rating = round(
                (
                    (kills / rounds) * 0.4 +
                    ((kills * 2 + data["assists"]) / rounds) * 0.3 +
                    ((rounds - deaths) / rounds) * 0.2 +
                    ((adr / 100) * 0.1)
                ) * 1.3,
                2
            )

            weapon_kills = []
            wmap = self._weapon_stats.get(str(sid), {})
            for w, ws in wmap.items():
                weapon_kills.append({
                    "weapon": w,
                    "kills": int(ws.get("kills", 0)),
                    "headshots": int(ws.get("headshots", 0)),
                    "damage": int(ws.get("damage", 0)),
                })
            weapon_kills.sort(key=lambda x: x["kills"], reverse=True)

            players_list.append({
                "nickname": (data["nickname"] or "").strip() if str(data["nickname"]).lower() not in ("nan", "none", "undefined") else "undefined",
                "steamid": (data["steamid"] or "").strip() if str(data["steamid"]).lower() not in ("nan", "none", "0") else str(sid),
                "team": (data["team"] or "").strip() or "undefined",
                "K": kills,
                "D": deaths,
                "A": data["assists"],
                "KD": kd,
                "HS": hs,
                "ADR": adr,
                "FK": data["first_kills"],
                "FD": data["first_deaths"],
                "rating": rating,
                "weapon_kills": weapon_kills,
            })

        players_list.sort(key=lambda x: x["rating"], reverse=True)

        halftime_round = 12

        first_half_ct = sum(
            1 for i in range(min(halftime_round, len(self.round_winners)))
            if self.round_winners[i] == "CT"
        )
        first_half_t = min(halftime_round, len(self.round_winners)) - first_half_ct

        second_half_ct = sum(
            1 for i in range(halftime_round, len(self.round_winners))
            if self.round_winners[i] == "CT"
        )
        second_half_t = (
            len(self.round_winners) - halftime_round - second_half_ct
            if len(self.round_winners) > halftime_round else 0
        )

        ct_players = [p for p in players_list if "CT" in p["team"].upper() or "COUNTER" in p["team"].upper()]
        t_players = [p for p in players_list if "T" in p["team"].upper() and "CT" not in p["team"].upper()]

        if not ct_players or not t_players:
            mid = len(players_list) // 2
            ct_players = players_list[:mid]
            t_players = players_list[mid:]

        team_started_ct_score = first_half_ct + second_half_t
        team_started_t_score = first_half_t + second_half_ct

        team_ct_name = ct_players[0]["nickname"] if ct_players else "Team 1"
        team_t_name = t_players[0]["nickname"] if t_players else "Team 2"

        if team_started_ct_score > team_started_t_score:
            winner_team = f"Team {team_ct_name} (started CT)"
        else:
            winner_team = f"Team {team_t_name} (started T)"

        return {
            "map": map_name,
            "total_rounds": self.total_rounds,
            "ct_score": self.ct_score,
            "t_score": self.t_score,
            "team1_score": team_started_ct_score,
            "team2_score": team_started_t_score,
            "team1_name": f"{team_ct_name}'s team",
            "team2_name": f"{team_t_name}'s team",
            "winner": winner_team,
            "first_half": {"ct": first_half_ct, "t": first_half_t},
            "second_half": {"ct": second_half_ct, "t": second_half_t},
            "players": players_list,
            "mvp": players_list[0] if players_list else None,
            "round_events": self.round_events
        }

    def _error(self, message: str) -> Dict[str, Any]:
        return {"error": message, "map": "Unknown", "total_rounds": 0, "players": [], "mvp": None, "round_events": []}