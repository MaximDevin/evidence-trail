# EvidenceTrail

**Autonomous agents that interpret market evidence and record the practice
trades they would make — with a tamper-evident, repeatable reasoning trail.**

Submission for the **Autonomous Agents** bounty ($6,000, sponsor RYO-CHAN) in
the BLI Legal Tech Hackathon 2 on DoraHacks.

- Zero dependencies (Python 3.10+ standard library only)
- No private keys, no exchange accounts, no real orders — every trade is a
  *practice* position in a local paper ledger
- All data comes from free, key-less public APIs

---

## 1. What it does

```
             +-------------------------------------------------+
             |                evidence bundle                  |
             |  Binance 24h tickers + 1h candles, CoinGecko     |
             |  spot cross-check, CoinDesk/Decrypt RSS, HN      |
             +-----------+------------------+------------------+
                         |                  |                  |
                 +-------v-------+  +-------v-------+  +-------v--------+
                 | NewsChecker   |  | Debate        |  | TokenHunter    |
                 | cause ->      |  | Bull vs Bear  |  | screen watch-  |
                 | effect verdict|  | from the SAME |  | list by 4      |
                 | per headline  |  | evidence,     |  | published      |
                 |               |  | Judge weighs  |  | numeric rules  |
                 +-------+-------+  +-------+-------+  +-------+--------+
                         |                  |                  |
                         +---------+--------+--------+---------+
                                     |                 |
                              +------v------+   +------v------+
                              | Buy-the-Dip |-->| Paper       |
                              | entry/sizing|   | Ledger      |
                              | /exit as one|   | risk limits |
                              | decision    |   | + stops     |
                              +------+------+   +-------------+
                                     |
                              +------v---------------------------+
                              | hash-chained reasoning trail      |
                              | data/trail.jsonl  (SHA-256 chain) |
                              +-----------------------------------+
```

Four agents, one paper account, one append-only trail.

| Agent | Direction from the bounty brief | What it produces |
|---|---|---|
| `NewsChecker` | *News Checker: verify a story, connect it with market evidence and explain its crypto impact* | per-headline assets, direction, score, explicit `cause` → `effect` |
| `BullAgent` / `BearAgent` / `DebateJudge` | *Bull/Bear Debate: opposing agents argue from the same evidence; a third judges* | both sides consume **identical evidence ids**; judge emits `risk-on`/`risk-off`/`neutral` with weights |
| `TokenHunter` | *Meme / Token Hunter: explain selected and rejected candidates* | per-candidate, per-rule pass/fail with the raw numbers |
| `DipBuyer` | *Buy the Dip Agent: treat entry, sizing and exit as one decision* | one atomic decision object (entry + size + stop + target + confidence), then the ledger may accept **or refuse** it |
| `Ledger` | *practice trades with user-defined risk limits* | positions, exposure, daily circuit breaker, rejections |

The special-project spotlight (*Multi-KOL Narrative Agent*) is deliberately
**not** faked: it needs X/Discord/Telegram API access we do not have. All data
sources used here are free and key-less, so the project runs for anyone.

## 2. The reasoning trail

Every step an agent takes is appended to `data/trail.jsonl` as:

```json
{
  "prev_hash": "<hash of previous entry>",
  "body": {
    "seq": 1, "ts": "2026-10-09T06:41:02Z",
    "agent": "NewsChecker", "ruleset": "news-checker/v1",
    "evidence_ids": ["3f0a…"],
    "rules": [{"id": "neg:exploit", "name": "negative cue", "detail": {"weight": -3}}],
    "inputs": {"cues": ["exploit"]},
    "conclusion": {"direction": "negative", "cause": "…", "effect": "…"}
  },
  "hash": "sha256(prev_hash || canonical(body))"
}
```

Three properties fall out of this:

1. **Traceable** – every conclusion lists the content-addressed evidence ids
   (`sha256` of the exact payload) it consumed, and the source URL is stored
   next to them, so any fact can be re-fetched and re-hashed.
2. **Tamper-evident** – `python -m evidencetrail verify` re-computes the chain;
   editing one historical conclusion breaks every later hash.
3. **Repeatable** – `python -m evidencetrail replay` re-runs every agent over
   the *stored* evidence bundle and diffs the conclusions against the recorded
   trail. Rules live in `evidencetrail/lexicon.py` with fixed ids and
   thresholds, so identical evidence ⇒ identical conclusions.

```
$ python -m evidencetrail verify
PASS: ok: 23 entries verified, head=07cc63afcab2e1c5...

$ python -m evidencetrail replay
PASS: 23 conclusions reproduced identically from stored evidence
```

## 3. Published rules (no black boxes)

**NewsChecker** (`lexicon.py`) – word-boundary matched cue lists with explicit
weights: `hack/exploit/breach… = -3`, `approval/etf/adoption… = +3`, etc.
Score > 0 ⇒ `positive`, < 0 ⇒ `negative`, else `neutral`; confidence is a
published function of |score| and asset coverage.

**Debate** – fixed weights, e.g. `bull.price_positive = 2`,
`bear.negative_news = 3`, `bear.near_24h_low = 2`. Both sides record the same
evidence id list; the judge entry stores `bull_weight`, `bear_weight` and the
shared-id count so the symmetry is auditable.

**TokenHunter** – four numeric gates, all editable in `lexicon.py`:

| id | rule | default |
|---|---|---|
| `liquidity` | 24h quote volume | ≥ 50,000,000 USD |
| `stability` | \|24h change\| | ≤ 25 % |
| `trend` | 24h change | ≥ −3 % |
| `data_quality` | price > 0, high ≥ low > 0 | must hold |

**Buy-the-Dip** – `entry, size, stop, target` are computed in one function:

* drawdown band from the last 30 candles must be in `[2 %, 12 %]` (hard gate)
* NewsChecker bias must not be `negative` (hard gate)
* debate verdict is a **soft** factor: `risk-on +0.10`, `risk-off −0.05`
  confidence (a dip buyer buys weakness by definition)
* `stop = entry × 0.97`, `target = entry × 1.05`
* size = `min(risk_budget / stop_distance, position_cap / entry)` with
  `risk_budget = 1 % of equity`, `position_cap = 10 % of equity`

**Ledger risk limits** (user-defined, all enforced, each refusal is logged
with the exact check that failed):

```
max_position_pct  = 10     max_exposure_pct = 30
max_open_positions= 3      max_daily_loss_pct = 3   (circuit breaker)
min_confidence    = 0.60
```

## 4. Data sources (free, no API keys)

| source | endpoint | used for |
|---|---|---|
| Binance public REST | `api.binance.com/api/v3/ticker/24hr`, `/klines` | 24h market state, 1h candles |
| CoinGecko public API | `api.coingecko.com/api/v3/simple/price` | independent spot cross-check |
| rss2json | CoinDesk + Decrypt RSS feeds | headlines |
| HN Algolia | `hn.algolia.com/api/v1/search` | developer-community signal |

Network failures fall back to captured fixtures in `fixtures/` (real data with
the original URL), so the demo is reproducible offline.

## 5. Run it

```bash
python -m evidencetrail collect    # fetch evidence -> data/evidence.json
python -m evidencetrail run        # live decision cycle (news, debate, screen, dip)
python -m evidencetrail simulate   # same rules replayed over captured 1h candles
python -m evidencetrail verify     # re-verify the hash chain
python -m evidencetrail replay     # reproduce every conclusion from stored evidence
python -m evidencetrail ledger     # practice-account summary
python -m unittest discover -s tests   # 21 unit tests
```

### Real output (2026-10-09, live data)

```
evidence items : 43
trail entries  : 23  (ok: 23 entries verified, head=07cc63afcab2e1c5...)

[NewsChecker] bias={'bias': 'negative', 'net_score': -2, 'confidence': 0.5, 'headlines': 12}
  negative conf=0.85  Ether bets were wiped out at six times bitcoin's rate in crypto's $1 billion flush
  positive conf=0.75  Bitcoin rebounds to $82,000 as Trump rules out Iran strikes, oil drops

[Debate] verdict=risk-off bull_w=15 bear_w=21 conf=0.8
  bull: ['BTCUSDT volume 1626M >= median', 'ETHUSDT volume 982M >= median', …]
  bear: ['BTCUSDT 24h -0.46% (momentum down)', 'ETHUSDT 24h -2.69%', 'SOLUSDT 24h -4.09%']

[TokenHunter] selected=['BTCUSDT', 'ETHUSDT'] rejected=['SOLUSDT', 'BNBUSDT', 'TRXUSDT']

[DipBuyer] BTCUSDT: REJECTED - confidence 0.0 >= 0.6   (adverse-news gate)
[DipBuyer] ETHUSDT: REJECTED - confidence 0.0 >= 0.6
[DipBuyer] SOLUSDT: REJECTED - confidence 0.0 >= 0.6
```

The live cycle **refused to trade** on 2026-10-09 because the news bias was
negative — the rejections are in the trail, which is the correct behaviour for
an agent whose rules say "do not buy the dip into adverse headlines".

```
$ python -m evidencetrail simulate
  BTCUSDT   candidate episodes= 39 accepted=0 opened=0
  ETHUSDT   candidate episodes= 18 accepted=2 opened=2
  SOLUSDT   candidate episodes= 40 accepted=1 opened=1

ledger: equity=9940.0 cash=7982.0 exposure=1988.0 rejected=97
closed practice trades=1  wins=0  losses=1  realised_pnl=-30.00
  P0001 ETHUSDT entry=2551.63 exit=2475.08 pnl=-30.00  trail=3598c11f9504
  P0002 ETHUSDT entry=2416.5 stop=2344.01 target=2537.33 (open)
  P0003 SOLUSDT entry=108.57 stop=105.313 target=113.998 (open)

backtest trail: 97 entries - ok: 97 entries verified
```

Same rules, replayed over the captured candle history: 97 candidate episodes,
3 accepted positions (one stopped out for −30.00, two still open), every
decision hash-chained. Note the stop and the target existed **before** the
position was opened — entry, sizing and exit are a single decision.

## 6. Project layout

```
evidencetrail/
  evidence.py      content-addressed evidence records
  sources.py       free public API collectors + fixture fallback
  lexicon.py       every rule, weight and threshold (the published rulebook)
  news_checker.py  NewsChecker agent
  debate.py        Bull / Bear / Judge agents
  token_hunter.py  TokenHunter agent
  dip_buyer.py     Buy-the-Dip agent (atomic decision function)
  backtest.py      walk-forward practice trades over captured candles
  ledger.py        paper ledger + risk limits
  trail.py         hash-chained reasoning trail
  __main__.py      CLI: collect | run | simulate | verify | replay | ledger
tests/             21 unit tests (offline, no network)
fixtures/          captured public-API responses for offline replay
data/              evidence bundle, trails, paper ledger
```

## 7. Limits & honesty notes

* The trail is tamper-*evident*, not blockchain-notarized; anchoring hashes
  on-chain would require a wallet signature we do not hold.
* News classification is rule/lexicon based (transparent and testable), not a
  language model — false positives/negatives are visible in the trail rather
  than hidden.
* Practice trades are simulated fills at candle close; no slippage/fees model.
* Nothing here can move funds: the project holds no keys and talks to no
  exchange endpoint that places orders.

MIT licensed.
