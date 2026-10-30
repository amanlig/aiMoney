# MU: three paths through the covered-call model

This example reproduces the saved **model v1.15** analysis. Subsequent configurable strike rules default to an inclusive midpoint boundary (`>=`); this historical capture used `>`. None of the illustrated replacement strikes equals the midpoint, so the worked arithmetic is unaffected.

Saved Questrade quote capture: **October 30, 2026 at 09:40:57 AM PDT**. All amounts are USD. Future prices are simulated. This report uses the first three paths from seed 42 and the same calculation helpers as the application. The production model remains at 600 paths.

## 1. Recorded position and accounting

The current position has 200 shares and two $115 calls expiring January 21, 2028. Each call covers 100 shares, so the option multiplier for the position is 200.

| Input | Value |
| --- | ---: |
| Stock purchase price per share | $89.62 |
| Stock purchase total | 200 × $89.62 = $17,924.00 |
| Recorded stock purchase fee | $6.95 |
| Total stock cost including fee | $17,930.95 |
| Recorded option sales, including replacements | $38,730.00 |
| Recorded option buybacks | $34,598.00 |
| Recorded option fees | $47.80 |
| Historical net option cash | $38,730 − $34,598 − $47.80 = $4,084.20 |

The latest call's $13,782 premium is already included in the recorded sales. It is not added a second time. Closed-call realized option P/L is -$9,697.80; adding the current call's $13,782 sale premium gives $4,084.20 cumulative option cash. Cash received and earned profit differ while an option liability is still open.

## 2. Captured market inputs and Close today

| Input | Bid | Ask | Midpoint |
| --- | ---: | ---: | ---: |
| MU stock | $883.97 | $884.23 | $884.10 |
| Held $115 January 2028 call | $769.50 | $783.70 | $776.60 |

Stock half-spread = ($884.23 − $883.97) / 2 = **$0.13**.

Close today uses midpoints:

```text
Stock proceeds          = 200 × 884.10 = 176,820.00
Held-call buyback       = 200 × 776.60 = 155,320.00
Closing cash            = 176,820.00 − 155,320.00 = 21,500.00
Total position P/L      = 21,500.00 + 4,084.20 − 17,930.95 = 7,653.25
```

Prospective rollover legs use the held-call ask and replacement bid instead of midpoints. Actual fills and future fees are not established by these quotes.

The captured continuous annual rate is **4.41413369%**, based on Treasury's October 29 observation matched to the held call's maturity. It is held fixed for this example.

## 3. Which replacement strikes are eligible?

```text
Purchase-price minimum = 1.2 × 89.62 = 107.544
Additional code rule   = replacement strike strictly above stock midpoint 884.10
```

Consequently, a $110 replacement does not qualify in this capture, even though it clears the purchase-price minimum. The stock-midpoint rule is the binding restriction. Actual listed strikes also need an allowed expiry, validated contract identity, usable two-sided quotes, sufficient option quote sizes, and a calibratable midpoint.

## 4. Generate three shared stock-price paths

There are 65 completed daily closes, ending October 29, producing 64 historical log returns. The October 30 unfinished daily close is excluded.

```text
Historical log return r = ln(next historical close / previous historical close)
Simulated next price   = previous simulated price × exp(r)
```

The random generator uses seed 42. Each daily return is sampled with replacement. Paths are generated once and reused for every contract. The historical date pair identifies the source of a sampled return; it is not a forecast calendar date.

| Path | First sampled historical closes | Log return | Multiplier | First simulated price |
| --- | --- | ---: | ---: | ---: |
| 1 | 2026-08-19 $937.11 → 2026-08-20 $974.33 | 0.0389494172 | 1.0397178905 | $884.10 × 1.0397178905 = $919.21 |
| 2 | 2026-10-07 $1,088.00 → 2026-10-08 $1,035.84 | -0.0491284897 | 0.9520587921 | $884.10 × 0.9520587921 = $841.72 |
| 3 | 2026-08-28 $932.86 → 2026-08-31 $958.73 | 0.0273543513 | 1.0277319164 | $884.10 × 1.0277319164 = $908.62 |

| Path | Day 0 | Day 10 | Day 30 |
| --- | ---: | ---: | ---: |
| 1 | $884.10 | $893.31 | $1,055.55 |
| 2 | $884.10 | $722.01 | $663.71 |
| 3 | $884.10 | $891.94 | $776.18 |

Every intermediate daily calculation appears at the end of this document.

## 5. Evaluate the three rollover contracts displayed in the saved analysis

The saved 600-path analysis selects these November 13, 2026 calls. We reevaluate the same three contracts with three paths for comparison; they need not remain the best contracts when using only three paths.

| Replacement strike | Captured bid | Captured ask | Midpoint | Calibrated annual IV | New premium received | Cash needed to roll |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| $1,050.00 | $3.35 | $3.55 | $3.450 | 58.974032% | $670.00 | $156,070.00 |
| $1,045.00 | $3.55 | $3.75 | $3.650 | 58.499691% | $710.00 | $156,030.00 |
| $1,020.00 | $5.10 | $5.25 | $5.175 | 56.987354% | $1,020.00 | $155,720.00 |

For the $1,050 replacement:

```text
Buy back held call      = 200 × 783.70 = 156,740.00
Sell replacement        = 200 × 3.35   =     670.00
Opening rollover cash   = 670.00 − 156,740.00 = -156,070.00
```

This is a large cash debit because the held $115 call is deep in the money and the replacement strike is much higher. This cash estimate does not establish available account cash or broker buying power. The current ranker does not exclude a contract because the debit might be unaffordable.

The code calibrates IV using Black–Scholes to match each current midpoint. For these calls it does not use Black–Scholes for Day 30 buyback valuation, because they expire first.

## 6. Check expiration at simulated Day 10

```text
Calendar days until Nov 13 = 14
Model expiry step          = ceil(14 × 252 / 365) = 10
```

All three Day 10 stock prices are below all three replacement strikes, so the calls expire worthless in these three paths. Their later buyback cost is zero. The model retains the shares until selling them at Day 30.

Path 1 reaches $1,055.55 by Day 30, but the $1,050 call had already expired when the stock was $893.31 on Day 10. Therefore that call does not cap the later stock sale in this path. If a call were in the money at its expiration step, the model would instead sell the covered shares at the strike and carry that cash forward to Day 30 at the interest rate. Early assignment is not modeled.

## 7. Sell the stock at Day 30 and discount the proceeds

```text
Estimated stock bid = Day 30 simulated stock price − captured $0.13 half-spread
Stock proceeds      = 200 × estimated stock bid
Horizon in years    = 30 / 252 = 0.119047619048
Discount factor D   = exp(-0.044141336881 × 30 / 252) = 0.994758861887
```

| Path | Day 30 stock price | Estimated stock bid | Stock proceeds | Present value of proceeds |
| --- | ---: | ---: | ---: | ---: |
| 1 | $1,055.55 | $1,055.42 | $211,083.03 | $209,976.71 |
| 2 | $663.71 | $663.58 | $132,715.57 | $132,019.99 |
| 3 | $776.18 | $776.05 | $155,210.34 | $154,396.86 |

The opening rollover cash occurs today and is not discounted. Only future proceeds and future buybacks are discounted. Equivalently, the code divides today's opening legs by D before aggregating and then multiplies the combined future-equivalent amounts by D.

## 8. Calculate each path's total position profit

```text
Present-value net cash = opening rollover cash + D × (future stock proceeds − future call buyback)
Total position P/L    = present-value net cash + historical option net cash − total stock cost
                      = present-value net cash + 4,084.20 − 17,930.95
                      = present-value net cash − 13,846.75
```

For Path 1 and the $1,050 November call:

```text
Present-value net cash = -156,070.00 + 209,976.712099 = 53,906.712099
Total position P/L    = 53,906.712099 + 4,084.20 − 17,930.95 = 40,059.962099
```

| Strike, November 13 | Path 1 total P/L | Path 2 total P/L | Path 3 total P/L | Mean total P/L |
| --- | ---: | ---: | ---: | ---: |
| $1,050.00 | $40,059.96 | -$37,896.76 | -$15,519.89 | -$4,452.23 |
| $1,045.00 | $40,099.96 | -$37,856.76 | -$15,479.89 | -$4,412.23 |
| $1,020.00 | $40,409.96 | -$37,546.76 | -$15,169.89 | -$4,102.23 |

For the $1,050 call, mean P/L = (40,059.962099 − 37,896.761624 − 15,519.890402) / 3 = **-$4,452.23**.

The recorded realized component stays -$9,697.80 across scenarios. The model's unrealized/prospective component is total scenario P/L minus that fixed realized component. Their sum equals the total P/L above.

The sale-price floor is 1.10 × $89.62 = $98.582. All three modeled stock sales exceed it, so these paths pass that flag. Only Path 1 beats the $7,653.25 Close today profit: a 1/3 path frequency, not a validated 33.3% probability.

## 9. Show where Day 30 Black–Scholes is needed

Use another actual listed MU call from the same capture: **$1,050 strike, January 21, 2028 expiry**. This is an additional explanatory contract, not one of the three displayed November choices.

```text
Replacement bid / ask = 168.55 / 174.15
Midpoint              = (168.55 + 174.15) / 2 = 171.35
Half-spread           = (174.15 − 168.55) / 2 = 2.80
Time to expiry today  = 448 / 365 = 1.227397260274 years
Calibrated IV sigma   = 0.544061241924 = 54.406124% annually
Opening rollover cash = 200 × 168.55 − 200 × 783.70 = -123,030.00
Time left at Day 30   = 448/365 − 30/252 = 1.108349641226 years
```

The model finds sigma by binary search until its call-price formula matches today's $171.35 midpoint. It uses its own midpoint calibration rather than directly taking the brokerage's reported IV field.

For each Day 30 stock price S, strike K=1050, remaining time t, sigma above and rate r:

```text
d1 = [ln(S/K) + (r + sigma²/2) × t] / [sigma × sqrt(t)]
d2 = d1 − sigma × sqrt(t)
C  = S × N(d1) − K × exp(-r × t) × N(d2)
Estimated buyback ask = C + 2.80
```

N is the standard normal cumulative distribution function. The code computes it with `erf`. Its formula assumes a European call with no dividends.

| Path | S at Day 30 | d1 | d2 | N(d1) | N(d2) | Theoretical call C | Estimated call ask |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | $1,055.55 | 0.381000148 | -0.191777657 | 0.648398431 | 0.423958187 | $260.51 | $263.31 |
| 2 | $663.71 | -0.429035725 | -1.001813530 | 0.333948613 | 0.158216831 | $63.45 | $66.25 |
| 3 | $776.18 | -0.155728047 | -0.728505852 | 0.438123694 | 0.233151994 | $106.94 | $109.74 |

Path 1 substitution (full precision retained in the calculations):

```text
d1 = [ln(1055.545136995316 / 1050) + (0.044141336881 + 0.544061241924²/2) × 1.108349641226]
     / [0.544061241924 × sqrt(1.108349641226)]
   = 0.381000148468

d2 = 0.381000148468 − 0.544061241924 × sqrt(1.108349641226)
   = -0.191777656850

K × exp(-r × t) = 999.866138234095
C = 1055.545136995316 × 0.648398430815 − 999.866138234095 × 0.423958186673
  = 260.512375600781

Estimated ask       = 260.512375600781 + 2.80 = 263.312375600781
Call buyback cost   = 200 × 263.312375600781 = 52,662.4751201561
Stock proceeds      = 200 × (1055.545136995316 − 0.13) = 211,083.0273990632
Future net proceeds = 211,083.0273990632 − 52,662.4751201561 = 158,420.5522789071
Present value       = 0.994758861887 × 158,420.5522789071 = 157,590.2482844809
Net cash including today's roll = -123,030 + 157,590.2482844809 = 34,560.2482844809
Total P/L           = 34,560.2482844809 + 4,084.20 − 17,930.95 = 20,713.4982844809
```

| Path | Future stock proceeds | Future call buyback | Future net proceeds | Discounted future net | Net cash including roll | Total P/L |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | $211,083.03 | $52,662.48 | $158,420.55 | $157,590.25 | $34,560.25 | $20,713.50 |
| 2 | $132,715.57 | $13,249.73 | $119,465.84 | $118,839.70 | -$4,190.30 | -$18,037.05 |
| 3 | $155,210.34 | $21,948.56 | $133,261.78 | $132,563.33 | $9,533.33 | -$4,313.42 |

Mean total P/L for this longer-dated call = **-$545.66** across the same three paths.
## 10. Rank the alternatives

Within the three displayed November candidates, three paths favor the $1,020 strike. The saved 600-path run favors $1,050. This happens because all three sampled paths expire below every one of those strikes, so the higher collected premium wins in this small sample. Other paths can cross the lower strike at expiry, changing assignment proceeds and the ranking.

If the full candidate universe is reranked with only these three paths, its top three are different again:

| Strike | Expiry | Mean total P/L with 3 paths |
| --- | --- | ---: |
| $895.00 | 2026-11-13 | $2,047.77 |
| $900.00 | 2026-11-13 | $1,587.77 |
| $895.00 | 2026-11-20 | $1,460.11 |

These results explain the mechanics; three paths are not a reliable performance estimate. The production run still uses 600 paths. More paths reduce sampling noise, not model-assumption error. Future transaction fees, taxes, dividends and early assignment are not modeled. Historical fees entered in the ledger are included.

## Complete daily arithmetic: all 90 simulated days

Each row applies one sampled historical daily return to the preceding simulated price. Displayed prices are rounded to cents; log returns and multipliers retain extra precision. Calculations use full precision before rounding for display.

### Path 1

| Day | Source dates | Historical closes | Log return | exp(return) | Previous simulated price | New simulated price |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 1 | 2026-08-19 → 2026-08-20 | 937.10998535 → 974.33001709 | 0.038949417174 | 1.039717890451 | $884.10 | $919.21 |
| 2 | 2026-08-04 → 2026-08-05 | 892.66998291 → 893.19000244 | 0.000582374374 | 1.000582543987 | $919.21 | $919.75 |
| 3 | 2026-09-18 → 2026-09-21 | 1015.79998779 → 1043.95996094 | 0.027344669765 | 1.027721966414 | $919.75 | $945.25 |
| 4 | 2026-09-14 → 2026-09-15 | 924.03002930 → 927.59997559 | 0.003856008709 | 1.003863452676 | $945.25 | $948.90 |
| 5 | 2026-09-09 → 2026-09-10 | 1027.77001953 → 977.40997314 | -0.050240516044 | 0.951000666073 | $948.90 | $902.40 |
| 6 | 2026-08-24 → 2026-08-25 | 910.42999268 → 932.96997070 | 0.024456007255 | 1.024757508220 | $902.40 | $924.75 |
| 7 | 2026-08-18 → 2026-08-19 | 940.76000977 → 937.10998535 | -0.003887413953 | 0.996120132259 | $924.75 | $921.16 |
| 8 | 2026-08-14 → 2026-08-17 | 971.65997314 → 1011.75000000 | 0.040430862365 | 1.041259317007 | $921.16 | $959.16 |
| 9 | 2026-10-15 → 2026-10-16 | 931.23999023 → 878.84002686 | -0.057914134248 | 0.943730978128 | $959.16 | $905.19 |
| 10 | 2026-08-05 → 2026-08-06 | 893.19000244 → 881.46997070 | -0.013208391812 | 0.986878456201 | $905.19 | $893.31 |
| 11 | 2026-08-04 → 2026-08-05 | 892.66998291 → 893.19000244 | 0.000582374374 | 1.000582543987 | $893.31 | $893.84 |
| 12 | 2026-08-14 → 2026-08-17 | 971.65997314 → 1011.75000000 | 0.040430862365 | 1.041259317007 | $893.84 | $930.71 |
| 13 | 2026-09-08 → 2026-09-09 | 1000.26000977 → 1027.77001953 | 0.027131449626 | 1.027502858754 | $930.71 | $956.31 |
| 14 | 2026-09-10 → 2026-09-11 | 977.40997314 → 975.26000977 | -0.002202076405 | 0.997800346387 | $956.31 | $954.21 |
| 15 | 2026-08-04 → 2026-08-05 | 892.66998291 → 893.19000244 | 0.000582374374 | 1.000582543987 | $954.21 | $954.76 |
| 16 | 2026-09-03 → 2026-09-04 | 958.15997314 → 1016.59002686 | 0.059194444060 | 1.060981522239 | $954.76 | $1,012.99 |
| 17 | 2026-10-14 → 2026-10-15 | 914.13000488 → 931.23999023 | 0.018544222265 | 1.018717234157 | $1,012.99 | $1,031.95 |
| 18 | 2026-09-09 → 2026-09-10 | 1027.77001953 → 977.40997314 | -0.050240516044 | 0.951000666073 | $1,031.95 | $981.38 |
| 19 | 2026-10-20 → 2026-10-21 | 896.07000732 → 913.66998291 | 0.019450894130 | 1.019641295258 | $981.38 | $1,000.66 |
| 20 | 2026-09-18 → 2026-09-21 | 1015.79998779 → 1043.95996094 | 0.027344669765 | 1.027721966414 | $1,000.66 | $1,028.40 |
| 21 | 2026-07-30 → 2026-07-31 | 874.65997314 → 823.03002930 | -0.060842521098 | 0.940971411254 | $1,028.40 | $967.69 |
| 22 | 2026-08-27 → 2026-08-28 | 935.39001465 → 932.85998535 | -0.002708449986 | 0.997295214555 | $967.69 | $965.08 |
| 23 | 2026-10-15 → 2026-10-16 | 931.23999023 → 878.84002686 | -0.057914134248 | 0.943730978128 | $965.08 | $910.77 |
| 24 | 2026-09-30 → 2026-10-01 | 1065.10998535 → 1097.39001465 | 0.029856580042 | 1.030306756805 | $910.77 | $938.37 |
| 25 | 2026-09-18 → 2026-09-21 | 1015.79998779 → 1043.95996094 | 0.027344669765 | 1.027721966414 | $938.37 | $964.39 |
| 26 | 2026-08-26 → 2026-08-27 | 938.40002441 → 935.39001465 | -0.003212753075 | 0.996792402294 | $964.39 | $961.29 |
| 27 | 2026-09-08 → 2026-09-09 | 1000.26000977 → 1027.77001953 | 0.027131449626 | 1.027502858754 | $961.29 | $987.73 |
| 28 | 2026-09-30 → 2026-10-01 | 1065.10998535 → 1097.39001465 | 0.029856580042 | 1.030306756805 | $987.73 | $1,017.67 |
| 29 | 2026-08-18 → 2026-08-19 | 940.76000977 → 937.10998535 | -0.003887413953 | 0.996120132259 | $1,017.67 | $1,013.72 |
| 30 | 2026-08-14 → 2026-08-17 | 971.65997314 → 1011.75000000 | 0.040430862365 | 1.041259317007 | $1,013.72 | $1,055.55 |
### Path 2

| Day | Source dates | Historical closes | Log return | exp(return) | Previous simulated price | New simulated price |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 1 | 2026-10-07 → 2026-10-08 | 1088.00000000 → 1035.83996582 | -0.049128489675 | 0.952058792114 | $884.10 | $841.72 |
| 2 | 2026-08-17 → 2026-08-18 | 1011.75000000 → 940.76000977 | -0.072748714142 | 0.929834454920 | $841.72 | $782.66 |
| 3 | 2026-10-02 → 2026-10-05 | 1074.89001465 → 1063.95996094 | -0.010220584877 | 0.989831467813 | $782.66 | $774.70 |
| 4 | 2026-10-01 → 2026-10-02 | 1097.39001465 → 1074.89001465 | -0.020716302112 | 0.979496806332 | $774.70 | $758.81 |
| 5 | 2026-09-16 → 2026-09-17 | 926.54998779 → 977.50000000 | 0.053530294224 | 1.054988951355 | $758.81 | $800.54 |
| 6 | 2026-08-06 → 2026-08-07 | 881.46997070 → 877.57000732 | -0.004434202540 | 0.995575614021 | $800.54 | $797.00 |
| 7 | 2026-10-21 → 2026-10-22 | 913.66998291 → 856.48999023 | -0.064626806356 | 0.937417236261 | $797.00 | $747.12 |
| 8 | 2026-08-20 → 2026-08-21 | 974.33001709 → 966.78002930 | -0.007779080718 | 0.992251098026 | $747.12 | $741.33 |
| 9 | 2026-10-07 → 2026-10-08 | 1088.00000000 → 1035.83996582 | -0.049128489675 | 0.952058792114 | $741.33 | $705.79 |
| 10 | 2026-08-13 → 2026-08-14 | 949.83001709 → 971.65997314 | 0.022722882185 | 1.022983013447 | $705.79 | $722.01 |
| 11 | 2026-09-22 → 2026-09-23 | 1096.16003418 → 1071.88000488 | -0.022399073814 | 0.977849922876 | $722.01 | $706.02 |
| 12 | 2026-10-05 → 2026-10-06 | 1063.95996094 → 1045.56005859 | -0.017445076424 | 0.982706207922 | $706.02 | $693.81 |
| 13 | 2026-09-02 → 2026-09-03 | 956.08001709 → 958.15997314 | 0.002173141178 | 1.002175504160 | $693.81 | $695.32 |
| 14 | 2026-08-11 → 2026-08-12 | 868.52001953 → 911.28997803 | 0.048070517882 | 1.049244643226 | $695.32 | $729.56 |
| 15 | 2026-08-06 → 2026-08-07 | 881.46997070 → 877.57000732 | -0.004434202540 | 0.995575614021 | $729.56 | $726.33 |
| 16 | 2026-09-10 → 2026-09-11 | 977.40997314 → 975.26000977 | -0.002202076405 | 0.997800346387 | $726.33 | $724.73 |
| 17 | 2026-09-22 → 2026-09-23 | 1096.16003418 → 1071.88000488 | -0.022399073814 | 0.977849922876 | $724.73 | $708.68 |
| 18 | 2026-08-13 → 2026-08-14 | 949.83001709 → 971.65997314 | 0.022722882185 | 1.022983013447 | $708.68 | $724.97 |
| 19 | 2026-09-10 → 2026-09-11 | 977.40997314 → 975.26000977 | -0.002202076405 | 0.997800346387 | $724.97 | $723.37 |
| 20 | 2026-08-17 → 2026-08-18 | 1011.75000000 → 940.76000977 | -0.072748714142 | 0.929834454920 | $723.37 | $672.62 |
| 21 | 2026-10-07 → 2026-10-08 | 1088.00000000 → 1035.83996582 | -0.049128489675 | 0.952058792114 | $672.62 | $640.37 |
| 22 | 2026-09-18 → 2026-09-21 | 1015.79998779 → 1043.95996094 | 0.027344669765 | 1.027721966414 | $640.37 | $658.12 |
| 23 | 2026-10-21 → 2026-10-22 | 913.66998291 → 856.48999023 | -0.064626806356 | 0.937417236261 | $658.12 | $616.94 |
| 24 | 2026-10-05 → 2026-10-06 | 1063.95996094 → 1045.56005859 | -0.017445076424 | 0.982706207922 | $616.94 | $606.27 |
| 25 | 2026-08-27 → 2026-08-28 | 935.39001465 → 932.85998535 | -0.002708449986 | 0.997295214555 | $606.27 | $604.63 |
| 26 | 2026-10-06 → 2026-10-07 | 1045.56005859 → 1088.00000000 | 0.039788465344 | 1.040590629928 | $604.63 | $629.17 |
| 27 | 2026-10-02 → 2026-10-05 | 1074.89001465 → 1063.95996094 | -0.010220584877 | 0.989831467813 | $629.17 | $622.77 |
| 28 | 2026-09-04 → 2026-09-08 | 1016.59002686 → 1000.26000977 | -0.016193939720 | 0.983936477185 | $622.77 | $612.77 |
| 29 | 2026-09-17 → 2026-09-18 | 977.50000000 → 1015.79998779 | 0.038433454490 | 1.039181573190 | $612.77 | $636.78 |
| 30 | 2026-08-12 → 2026-08-13 | 911.28997803 → 949.83001709 | 0.041421885210 | 1.042291740271 | $636.78 | $663.71 |
### Path 3

| Day | Source dates | Historical closes | Log return | exp(return) | Previous simulated price | New simulated price |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 1 | 2026-08-28 → 2026-08-31 | 932.85998535 → 958.72998047 | 0.027354351302 | 1.027731916390 | $884.10 | $908.62 |
| 2 | 2026-09-14 → 2026-09-15 | 924.03002930 → 927.59997559 | 0.003856008709 | 1.003863452676 | $908.62 | $912.13 |
| 3 | 2026-08-27 → 2026-08-28 | 935.39001465 → 932.85998535 | -0.002708449986 | 0.997295214555 | $912.13 | $909.66 |
| 4 | 2026-10-22 → 2026-10-23 | 856.48999023 → 877.54998779 | 0.024291288992 | 1.024588725845 | $909.66 | $932.03 |
| 5 | 2026-10-07 → 2026-10-08 | 1088.00000000 → 1035.83996582 | -0.049128489675 | 0.952058792114 | $932.03 | $887.35 |
| 6 | 2026-09-17 → 2026-09-18 | 977.50000000 → 1015.79998779 | 0.038433454490 | 1.039181573190 | $887.35 | $922.11 |
| 7 | 2026-09-09 → 2026-09-10 | 1027.77001953 → 977.40997314 | -0.050240516044 | 0.951000666073 | $922.11 | $876.93 |
| 8 | 2026-09-28 → 2026-09-29 | 1053.97998047 → 1065.07995605 | 0.010476416375 | 1.010531486168 | $876.93 | $886.17 |
| 9 | 2026-08-10 → 2026-08-11 | 861.00000000 → 868.52001953 | 0.008696131686 | 1.008734052882 | $886.17 | $893.91 |
| 10 | 2026-09-10 → 2026-09-11 | 977.40997314 → 975.26000977 | -0.002202076405 | 0.997800346387 | $893.91 | $891.94 |
| 11 | 2026-08-05 → 2026-08-06 | 893.19000244 → 881.46997070 | -0.013208391812 | 0.986878456201 | $891.94 | $880.24 |
| 12 | 2026-09-25 → 2026-09-28 | 1082.28002930 → 1053.97998047 | -0.026496497977 | 0.973851454280 | $880.24 | $857.22 |
| 13 | 2026-10-12 → 2026-10-13 | 989.03997803 → 953.19000244 | -0.036920496729 | 0.963752753799 | $857.22 | $826.15 |
| 14 | 2026-09-17 → 2026-09-18 | 977.50000000 → 1015.79998779 | 0.038433454490 | 1.039181573190 | $826.15 | $858.52 |
| 15 | 2026-08-11 → 2026-08-12 | 868.52001953 → 911.28997803 | 0.048070517882 | 1.049244643226 | $858.52 | $900.79 |
| 16 | 2026-09-08 → 2026-09-09 | 1000.26000977 → 1027.77001953 | 0.027131449626 | 1.027502858754 | $900.79 | $925.57 |
| 17 | 2026-09-25 → 2026-09-28 | 1082.28002930 → 1053.97998047 | -0.026496497977 | 0.973851454280 | $925.57 | $901.37 |
| 18 | 2026-09-08 → 2026-09-09 | 1000.26000977 → 1027.77001953 | 0.027131449626 | 1.027502858754 | $901.37 | $926.16 |
| 19 | 2026-10-28 → 2026-10-29 | 983.22998047 → 934.27001953 | -0.051077553946 | 0.950204975530 | $926.16 | $880.04 |
| 20 | 2026-10-09 → 2026-10-12 | 1029.00000000 → 989.03997803 | -0.039607982352 | 0.961166159405 | $880.04 | $845.86 |
| 21 | 2026-10-21 → 2026-10-22 | 913.66998291 → 856.48999023 | -0.064626806356 | 0.937417236261 | $845.86 | $792.93 |
| 22 | 2026-08-25 → 2026-08-26 | 932.96997070 → 938.40002441 | 0.005803308768 | 1.005820180586 | $792.93 | $797.54 |
| 23 | 2026-09-16 → 2026-09-17 | 926.54998779 → 977.50000000 | 0.053530294224 | 1.054988951355 | $797.54 | $841.40 |
| 24 | 2026-08-24 → 2026-08-25 | 910.42999268 → 932.96997070 | 0.024456007255 | 1.024757508220 | $841.40 | $862.23 |
| 25 | 2026-09-14 → 2026-09-15 | 924.03002930 → 927.59997559 | 0.003856008709 | 1.003863452676 | $862.23 | $865.56 |
| 26 | 2026-09-16 → 2026-09-17 | 926.54998779 → 977.50000000 | 0.053530294224 | 1.054988951355 | $865.56 | $913.16 |
| 27 | 2026-10-15 → 2026-10-16 | 931.23999023 → 878.84002686 | -0.057914134248 | 0.943730978128 | $913.16 | $861.77 |
| 28 | 2026-10-12 → 2026-10-13 | 989.03997803 → 953.19000244 | -0.036920496729 | 0.963752753799 | $861.77 | $830.54 |
| 29 | 2026-10-05 → 2026-10-06 | 1063.95996094 → 1045.56005859 | -0.017445076424 | 0.982706207922 | $830.54 | $816.17 |
| 30 | 2026-09-09 → 2026-09-10 | 1027.77001953 → 977.40997314 | -0.050240516044 | 0.951000666073 | $816.17 | $776.18 |

## Related implementation

- [Covered-call model](../models/financials/covered_call_exit/model.py)
- [UI-to-model sequence diagrams](../README.md#from-the-ui-to-the-covered-call-model)
