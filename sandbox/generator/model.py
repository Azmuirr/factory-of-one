from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

from . import baseline as B
from .baseline import DAY
from .scenario import Action, Scenario
from .text import baseline_template, render

# Stream ids keep randomness independent per purpose, so an action changes only what it should.
NONVIRAL, WORKSPACE, VIRAL, TICKETS = 0, 1, 2, 3


def pick(rng, weights: dict):
    keys = list(weights)
    p = np.array([weights[k] for k in keys], dtype=float)
    return keys[int(rng.choice(len(keys), p=p / p.sum()))]


def short_id(prefix: str, *parts) -> str:
    return prefix + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:10]


@dataclass
class Workspace:
    workspace_id: str
    user_id: str
    created_at: float
    channel: str
    company_size: str
    calendar_provider: str
    meeting_platform: str
    referrer_workspace_id: str | None
    requires_admin_consent: bool
    p_base: float
    blocked_by: str | None = None
    releases_applied: list[str] = field(default_factory=list)
    activated_at: float | None = None


@dataclass
class World:
    workspaces: list[Workspace] = field(default_factory=list)
    events: list[tuple] = field(default_factory=list)  # (ts, event_id, workspace_id, user_id, product, name, props)
    subscriptions: list[tuple] = field(default_factory=list)  # (ts, workspace_id, plan, seats, billing, mrr)
    tickets: list[tuple] = field(default_factory=list)  # (ts, ticket_id, workspace_id, user_id, subject, body, tag)


class Simulator:
    def __init__(self, scenario: Scenario, seed: int, actions: list[Action]):
        self.scenario = scenario
        self.seed = seed
        self.actions = actions
        self.world = World()
        self.ticket_theme = next(iter(scenario.ticket_themes), None)

    def rng(self, *parts) -> np.random.Generator:
        return np.random.default_rng([self.seed, *parts])

    # Release effects -------------------------------------------------------

    def active_effects(self, ws: Workspace, t: float) -> dict:
        segment = {
            "calendar_provider": ws.calendar_provider,
            "company_size": ws.company_size,
            "channel": ws.channel,
        }
        merged: dict = {}
        for release in self.scenario.releases:
            if not release.effects or t < release.ts or self.rolled_back(release.id, segment, t):
                continue
            applied = False
            for effect in release.effects:
                wanted = effect.get("segment") or {}
                if not all(segment.get(k) in v for k, v in wanted.items()):
                    continue
                applied = True
                merged.update({k: v for k, v in effect.items() if k not in ("kind", "segment")})
                if effect["kind"] == "connect_block":
                    merged["block_release"] = release.id
                elif effect["kind"] == "paid_friction":
                    merged["friction_release"] = release.id
                elif effect["kind"] == "share_block":
                    merged["share_release"] = release.id
            if applied:
                ws.releases_applied.append(release.id)
        return merged

    def rolled_back(self, release_id: str, segment: dict, t: float) -> bool:
        return any(
            a.name == "rollback"
            and a.params.get("release_id") == release_id
            and a.effective_from <= t
            and a.matches(segment)
            for a in self.actions
        )

    # Arrivals --------------------------------------------------------------

    def run(self, n_days: int) -> World:
        activations = np.zeros(n_days + B.VIRAL_WINDOW_DAYS + 30)
        offset = B.VIRAL_WINDOW_DAYS
        for d in range(-offset, 0):
            activations[d + offset] = B.PRE_HISTORY_ACTIVATIONS_PER_DAY * B.WEEKDAY_FACTOR[d % 7]
        recent_activated: list[tuple[int, str]] = []

        for d in range(n_days):
            weekday = B.WEEKDAY_FACTOR[d % 7]
            base = B.NONVIRAL_PER_DAY * weekday * (1 + B.WEEKLY_TREND) ** (d / 7)
            n_nonviral = int(self.rng(d, NONVIRAL).poisson(base))
            window = activations[d : d + offset].sum()
            n_viral = int(self.rng(d, VIRAL).poisson(B.VIRAL_K / B.VIRAL_WINDOW_DAYS * window))

            pool = [ws_id for day, ws_id in recent_activated if d - B.VIRAL_WINDOW_DAYS <= day < d]
            existing = len(self.world.workspaces)
            for i in range(n_nonviral + n_viral):
                rng = self.rng(d, WORKSPACE, i)
                viral = i >= n_nonviral
                referrer = pool[int(rng.integers(len(pool)))] if viral and pool else None
                ws = self.new_workspace(rng, d, i, viral, referrer)
                self.lifecycle(ws, rng)
                self.world.workspaces.append(ws)
                if ws.activated_at is not None:
                    share_day = int(ws.activated_at // DAY)
                    activations[share_day + offset] += 1
                    recent_activated.append((share_day, ws.workspace_id))

            self.baseline_tickets(d, self.world.workspaces[:existing])
        return self.world

    def new_workspace(self, rng, d: int, i: int, viral: bool, referrer: str | None) -> Workspace:
        channel = "recap_link" if viral else pick(rng, B.NONVIRAL_CHANNELS)
        size = pick(rng, B.COMPANY_SIZE)
        provider = pick(rng, B.CALENDAR)
        platform = pick(rng, B.MEETING_PLATFORM[provider])
        hour = float(np.clip(rng.normal(16, 3.5), 0, 23.99))  # business hours, mostly Americas and Europe
        p_base = (
            B.BASE_ACTIVATION[provider]
            * B.CHANNEL_MULT[channel] / B.CHANNEL_NORM
            * B.SIZE_MULT[size] / B.SIZE_NORM
        )
        return Workspace(
            workspace_id=short_id("ws_", self.seed, d, i),
            user_id=short_id("u_", self.seed, d, i),
            created_at=d * DAY + hour * 3600,
            channel=channel,
            company_size=size,
            calendar_provider=provider,
            meeting_platform=platform,
            referrer_workspace_id=referrer,
            requires_admin_consent=bool(rng.random() < B.ADMIN_CONSENT_SHARE[provider]),
            p_base=min(p_base, 0.95),
        )

    # One workspace, signup to trial end -------------------------------------

    def lifecycle(self, ws: Workspace, rng) -> None:
        u_activate, u_paid, u_ticket = rng.random(3)
        events: list[tuple[float, str, dict]] = []
        t0 = ws.created_at
        effects = self.active_effects(ws, t0)
        skippable = effects.get("calendar_step_skippable", True)

        t = t0
        events.append((t, "signup_completed", {}))
        t += rng.uniform(5, 40)
        events.append((t, "onboarding_step_viewed", {"step": "welcome"}))

        blocked = False
        provider = ws.calendar_provider
        if provider != "none":
            t += rng.uniform(10, 60)
            events.append((t, "onboarding_step_viewed", {"step": "calendar_connect"}))
            attempt = (not skippable) or rng.random() < B.CALENDAR_ATTEMPT_V1[provider]
            if not attempt:
                events.append((t + rng.uniform(3, 15), "onboarding_step_skipped", {"step": "calendar_connect"}))
            else:
                t += rng.uniform(5, 30)
                events.append((t, "calendar_connect_started", {"provider": provider}))
                t += rng.uniform(5, 40)
                if ws.requires_admin_consent:
                    events.append((t, "calendar_connect_failed", {"provider": provider, "error_code": "admin_consent_required"}))
                    if skippable:
                        events.append((t + rng.uniform(3, 20), "onboarding_step_skipped", {"step": "calendar_connect"}))
                    else:
                        blocked = True
                        if rng.random() < 0.5:
                            t += rng.uniform(60, 600)
                            events.append((t, "calendar_connect_started", {"provider": provider}))
                            events.append((t + rng.uniform(5, 40), "calendar_connect_failed", {"provider": provider, "error_code": "admin_consent_required"}))
                elif rng.random() < B.CONNECT_CANCEL_RATE:
                    events.append((t, "calendar_connect_failed", {"provider": provider, "error_code": "user_cancelled"}))
                    if skippable:
                        events.append((t + rng.uniform(3, 20), "onboarding_step_skipped", {"step": "calendar_connect"}))
                    else:
                        t += rng.uniform(30, 300)
                        events.append((t, "calendar_connect_started", {"provider": provider}))
                        events.append((t + rng.uniform(5, 40), "calendar_connect_completed", {"provider": provider}))
                else:
                    events.append((t, "calendar_connect_completed", {"provider": provider}))

        p_activate = ws.p_base
        if blocked:
            ws.blocked_by = effects["block_release"]
            p_activate *= effects["activation_retained"]
            if self.ticket_theme and u_ticket < self.ticket_theme["file_rate"]:
                self.planted_ticket(ws, rng, t + rng.uniform(0.1, 2.0) * DAY)

        activated = u_activate < p_activate
        deadline = t0 + 7 * DAY - 60
        if activated:
            start = t
            if blocked:
                start = t + rng.uniform(1, 4) * DAY
                events.append((start, "calendar_connect_started", {"provider": provider}))
                events.append((start + 30, "calendar_connect_completed", {"provider": provider}))
            meet_t = min(start + rng.lognormal(math.log(20 * 3600), 0.8), deadline - 4 * 3600)
            meet_t = max(meet_t, start + 60)
            share_t = self.meeting(ws, rng, meet_t, events, share_within=deadline, share_prob=effects.get("share_retained", 1.0))
            ws.activated_at = share_t
            if share_t is None and "share_release" in effects and self.ticket_theme and u_ticket < self.ticket_theme["file_rate"]:
                self.planted_ticket(ws, rng, meet_t + rng.uniform(0.1, 1.0) * DAY)
            for _ in range(int(rng.poisson(2))):
                self.meeting(ws, rng, t0 + rng.uniform(1, 14) * DAY, events, share_prob=0.6)
        else:
            if rng.random() < 0.3:
                test_t = t + rng.uniform(60, 1 * DAY)
                events.append((test_t, "meeting_recorded", {
                    "meeting_id": short_id("m_", ws.workspace_id, test_t),
                    "meeting_platform": ws.meeting_platform,
                    "duration_min": int(rng.integers(1, 5)),
                    "participants": 1,
                }))
            if rng.random() < 0.4:
                meet_t = t0 + rng.uniform(0.2, 13) * DAY
                late_share = meet_t > t0 + 7 * DAY and rng.random() < 0.3
                self.meeting(ws, rng, meet_t, events, share_prob=1.0 if late_share else 0.0)

        self.trial_end(ws, rng, u_paid, activated, events, effects)
        for k, (ts, name, props) in enumerate(sorted(events, key=lambda e: e[0])):
            self.world.events.append((ts, f"{ws.workspace_id}-{k:03d}", ws.workspace_id, ws.user_id, "notes", name, props))

    def meeting(self, ws, rng, t, events, share_within=None, share_prob=1.0) -> float | None:
        platform = ws.meeting_platform if rng.random() < 0.85 else pick(rng, B.MEETING_PLATFORM[ws.calendar_provider])
        duration = int(np.clip(rng.lognormal(math.log(30), 0.5), 5, 180))
        participants = int(min(2 + rng.poisson(2.5), 12))
        meeting_id = short_id("m_", ws.workspace_id, t)
        events.append((t, "meeting_recorded", {
            "meeting_id": meeting_id,
            "meeting_platform": platform,
            "duration_min": duration,
            "participants": participants,
        }))
        if rng.random() >= share_prob:
            return None
        share_t = t + duration * 60 + rng.uniform(300, 3 * 3600)
        if share_within is not None:
            share_t = min(share_t, share_within)
        recipients = int(min(participants - 1, 1 + rng.poisson(1.5)))
        events.append((share_t, "recap_shared", {
            "meeting_id": meeting_id,
            "recipients": recipients,
            "external_recipients": int(rng.binomial(recipients, 0.35)),
        }))
        return share_t

    def trial_end(self, ws, rng, u_paid, activated, events, effects=None) -> None:
        subs = self.world.subscriptions
        subs.append((ws.created_at, ws.workspace_id, "trial", 1, None, 0.0))
        end_t = ws.created_at + B.TRIAL_DAYS * DAY
        paid_mult = (effects or {}).get("paid_mult", 1.0)
        paid = u_paid < (B.PAID_IF_ACTIVATED if activated else B.PAID_IF_NOT) * paid_mult
        events.append((end_t, "trial_ended", {"outcome": "paid" if paid else "free"}))
        if not paid:
            subs.append((end_t, ws.workspace_id, "free", 1, None, 0.0))
            if paid_mult < 1.0 and self.ticket_theme and rng.random() < self.ticket_theme["file_rate"]:
                self.planted_ticket(ws, rng, end_t + rng.uniform(0.1, 2.0) * DAY)
            return
        if ws.company_size == "solo":
            plan, seats = "pro", 1
        else:
            plan = "business" if rng.random() < B.BUSINESS_SHARE_OF_TEAMS else "team"
            low, high = B.SEATS[ws.company_size]
            seats = int(rng.integers(low, high + 1))
        billing = "annual" if rng.random() < B.ANNUAL_SHARE else "monthly"
        monthly, annual = B.PRICE[plan]
        subs.append((end_t, ws.workspace_id, plan, seats, billing, float(seats * (annual if billing == "annual" else monthly))))

    # Support tickets -------------------------------------------------------

    def planted_ticket(self, ws: Workspace, rng, t: float) -> None:
        theme = self.ticket_theme
        subject, body = render(
            theme["template"], rng,
            provider=B.PROVIDER_NAME[ws.calendar_provider],
            platform=B.PLATFORM_NAME[ws.meeting_platform],
        )
        tag = pick(rng, theme["support_tag_mix"])
        ticket_id = short_id("t_", ws.workspace_id, t)
        self.world.tickets.append((t, ticket_id, ws.workspace_id, ws.user_id, subject, body, tag))

    def baseline_tickets(self, d: int, eligible: list[Workspace]) -> None:
        rng = self.rng(d, TICKETS)
        n = int(rng.poisson(B.TICKETS_PER_DAY * B.WEEKDAY_FACTOR[d % 7]))
        for _ in range(n if eligible else 0):
            ws = eligible[int(rng.integers(len(eligible)))]
            theme = pick(rng, B.TICKET_THEMES)
            t = d * DAY + rng.uniform(0, DAY)
            subject, body = render(
                baseline_template(theme), rng,
                provider=B.PROVIDER_NAME[ws.calendar_provider],
                platform=B.PLATFORM_NAME[ws.meeting_platform],
            )
            tag = pick(rng, B.TICKET_TAGS[theme])
            ticket_id = short_id("t_", ws.workspace_id, t)
            self.world.tickets.append((t, ticket_id, ws.workspace_id, ws.user_id, subject, body, tag))
