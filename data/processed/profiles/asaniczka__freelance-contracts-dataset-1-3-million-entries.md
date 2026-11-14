# Profile: asaniczka/freelance-contracts-dataset-1-3-million-entries

- source: https://www.kaggle.com/datasets/asaniczka/freelance-contracts-dataset-1-3-million-entries
- title: Freelance Contracts Dataset (1.3 Million Entries)
- subtitle: Contains 1.3 million freelance contracts from a popular freelancing website
- licence (from Kaggle metadata): **ODC Attribution License (ODC-By)**
- downloaded (UTC): 2026-11-14T21:54:35Z

## Files

| file | bytes |
|---|---|
| `contracts.csv` | 162,774,789 |
| `dataset-metadata.json` | 1,374 |

## Contents

### `contracts.csv`

- rows: **1,292,791**
- columns: **8**
- exact duplicate rows: 0

| # | column | dtype | null % | distinct | example |
|---|---|---|---|---|---|
| 0 | `job_id` | str | 0.0 | 1,292,791 | 1809027255792620477 |
| 1 | `job_title` | str | 0.0 | 1,141,821 | English to Chinese Translation |
| 2 | `start_date` | str | 0.0 | 1,178,773 | 2024-07-08 00:20:55.228 |
| 3 | `end_date` | str | 30.7 | 879,725 | 2023-11-08 22:29:32 |
| 4 | `freelancer_id` | str | 0.0 | 92,933 | ~0196cdd32832cc78a8 |
| 5 | `total_hours` | float64 | 0.0 | 55,362 | 3.5 |
| 6 | `total_paid` | float64 | 0.0 | 130,140 | 122.5 |
| 7 | `hourly_rate` | float64 | 61.6 | 2,868 | 35.0 |

Numeric summary:

|             |            count |    mean |     std |   min |   25% |    50% |    75% |             max |
|:------------|-----------------:|--------:|--------:|------:|------:|-------:|-------:|----------------:|
| total_hours |      1.29279e+06 |   58.91 |  382.52 |     0 |     0 |   0    |  11.67 | 37621           |
| total_paid  |      1.29279e+06 | 1311.27 | 8162.34 |     0 |    20 | 111.66 | 500    |     1.32216e+06 |
| hourly_rate | 496044           |   31.77 |   34.93 |     0 |    10 |  20    |  40    |   999           |

5 sample rows (seeded, text truncated):

|              job_id | job_title                                                                                           | start_date              | end_date            | freelancer_id       |   total_hours |   total_paid |   hourly_rate |
|--------------------:|:----------------------------------------------------------------------------------------------------|:------------------------|:--------------------|:--------------------|--------------:|-------------:|--------------:|
| 1288734710747328512 | Vulnarability test                                                                                  | 2020-07-31 10:16:35     | 2020-08-01 06:18:22 | ~0193d06788d9bafe86 |             0 |        200   |               |
| 1456146839149727744 | Science journalism articles and interviews                                                          | 2021-11-15 10:24:03     | 2021-12-17 05:13:21 | ~0142a6a7d22ffcac65 |            10 |        300   |            30 |
| 1597121553766772736 | Finish Exchange 2019 migration to another server (already 80% done) WILL HIRE IN THE NEXT FEW HOURS | 2022-11-28 06:54:34     |                     | ~01f118ec36da213edf |             0 |         29.7 |               |
| 1484174900208783360 | two power point explain google ads                                                                  | 2022-01-20 14:49:29     |                     | ~018baabda2aa391c4a |             0 |          0   |               |
| 1816045606287076187 | structural calculations for 2 x 4 units townhouses located in Melbourne Florida                     | 2024-07-25 13:00:03.429 |                     | ~015d06e38a38abaeb1 |             0 |          0   |               |
