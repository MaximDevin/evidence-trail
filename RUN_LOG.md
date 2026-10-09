# Run log — real terminal output

Captured 2026-10-09 on the submission machine. Live public data, no keys.

## 1. Unit tests

```
----------------------------------------------------------------------
Ran 21 tests in 0.018s

OK
```

## 2. `python -m evidencetrail run` (live decision cycle)

```
========================================================================
EvidenceTrail run report
========================================================================
evidence items : 43
trail entries  : 23  (ok: 23 entries verified, head=07cc63afcab2e1c5...)

[NewsChecker] bias={'bias': 'negative', 'net_score': -2, 'confidence': 0.5, 'headlines': 12} over 12 headlines
  positive conf=0.75  Solana is about to halve its block times as final 200-millisecond upgrade nears
  positive conf=0.50  XRP Ledger adds new controls for banks, stablecoins and tokenized funds
  negative conf=0.85  Ether bets were wiped out at six times bitcoin’s rate in crypto’s $1 billion flu
  positive conf=0.75  Bitcoin rebounds to $82,000 as Trump rules out Iran strikes, oil drops
  neutral  conf=0.30  Top Democrat among Senate investigators probes ties between Cantor Fitzgerald, T

[Debate] verdict=risk-off bull_w=15 bear_w=21 conf=0.8
  bull: ['BTCUSDT volume 1626M >= median', 'ETHUSDT volume 982M >= median', 'SOLUSDT volume 396M >= median']
  bear: ['BTCUSDT 24h -0.46% (momentum down)', 'ETHUSDT 24h -2.69% (momentum down)', 'SOLUSDT 24h -4.09% (momentum down)']

[TokenHunter] selected=['BTCUSDT', 'ETHUSDT'] rejected=['SOLUSDT', 'BNBUSDT', 'TRXUSDT']

[DipBuyer] BTCUSDT: REJECTED - REJECTED by risk limits -> confidence: confidence 0.0 >= 0.6
[DipBuyer] ETHUSDT: REJECTED - REJECTED by risk limits -> confidence: confidence 0.0 >= 0.6
[DipBuyer] SOLUSDT: REJECTED - REJECTED by risk limits -> confidence: confidence 0.0 >= 0.6

[Ledger] equity=10000.0 cash=10000.0 exposure=0 daily_pnl=0.0% rejected=3

verify: ok: 23 entries verified, head=07cc63afcab2e1c5...
```

## 3. `python -m evidencetrail simulate` (walk-forward practice trades)

```
========================================================================
Walk-forward practice trades (same rules, replayed over 1h candles)
========================================================================
news bias used as gate: {'bias': 'neutral', 'net_score': 0, 'confidence': 0.4, 'headlines': 20}
  BTCUSDT   candidate episodes= 39 accepted=0 opened=0
  ETHUSDT   candidate episodes= 18 accepted=2 opened=2
  SOLUSDT   candidate episodes= 40 accepted=1 opened=1

ledger: equity=9940.0 cash=7982.0 exposure=1988.0 rejected=97
closed practice trades=1  wins=0  losses=1  realised_pnl=-30.00
  P0001 ETHUSDT entry=2551.63 exit=2475.08 pnl=-30.00  trail=3598c11f9504
  P0002 ETHUSDT entry=2416.5 stop=2344.01 target=2537.33 (open)
  P0003 SOLUSDT entry=108.57 stop=105.313 target=113.998 (open)

backtest trail: 97 entries - ok: 97 entries verified, head=0a3c7ead9abb3450...
```

## 4. `python -m evidencetrail verify` + `replay`

```
PASS: ok: 23 entries verified, head=07cc63afcab2e1c5...
PASS: 23 conclusions reproduced identically from stored evidence (ok: 23 entries verified, head=95f5ab9cc2dd7cbc...)
```
