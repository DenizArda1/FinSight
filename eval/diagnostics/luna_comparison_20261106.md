| System | Cases | Reviewed | Released | Numeric | Citation precision | Citation coverage | Faithfulness | Advice refusal | False refusal (judged answers) | Direct injection | Mean seconds | Tokens | Estimated USD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline | 37 | 37/37 | 37/37 | 6.7% | 37.5% | 23.7% | 22.9% | 100.0% | 41.4% | 100.0% | 4.29 | 14330 | 0.006109 |
| naive_rag | 37 | 37/37 | 37/37 | 20.0% | 64.1% | 74.0% | 76.3% | 100.0% | 13.8% | 100.0% | 2.95 | 83463 | 0.010973 |
| multi_agent | 37 | 37/37 | 32/37 | 93.3% | 100.0% | 83.5% | 97.6% | 100.0% | 8.3% | 100.0% | 24.82 | 551644 | 0.025245 |

N/A means unmeasured, not success. Review scores are model judgments until human calibration. Costs exclude evaluation-judge calls and local hardware; inspect usage coverage in each run.
Advice refusal and direct injection use their designated case categories only; missing/error reviews do not count as passes. False refusal covers judged released answers only: inspect Released and withheld cases separately, as a withheld answer is not automatically a proven false rejection.
