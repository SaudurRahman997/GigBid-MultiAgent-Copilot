# Profile: sarveshchhetri/freelancer-success-earnings-and-churn-prediction

- source: https://www.kaggle.com/datasets/sarveshchhetri/freelancer-success-earnings-and-churn-prediction
- title: Freelancer Marketplace Dataset for ML & Analytics
- subtitle: 12k real-world style records to predict earnings, success score & dropout risk
- licence (from Kaggle metadata): **apache-2.0**
- downloaded (UTC): 2026-11-14T21:54:43Z

## Files

| file | bytes |
|---|---|
| `dataset-metadata.json` | 2,522 |
| `freelancer_gig_success_dataset.csv` | 1,277,200 |

## Contents

### `freelancer_gig_success_dataset.csv`

- rows: **12,000**
- columns: **20**
- exact duplicate rows: 0

| # | column | dtype | null % | distinct | example |
|---|---|---|---|---|---|
| 0 | `freelancer_id` | str | 0.0 | 12,000 | FL_000000 |
| 1 | `age` | int64 | 0.0 | 31 | 27 |
| 2 | `gender` | str | 0.0 | 3 | Female |
| 3 | `country` | str | 0.0 | 11 | United Kingdom |
| 4 | `years_experience` | float64 | 0.0 | 197 | 3.3 |
| 5 | `num_skills` | int64 | 0.0 | 12 | 15 |
| 6 | `profile_completeness` | float64 | 0.0 | 598 | 51.4 |
| 7 | `has_portfolio` | int64 | 0.0 | 2 | 1 |
| 8 | `has_video_profile` | int64 | 0.0 | 2 | 0 |
| 9 | `has_certifications` | float64 | 0.2 | 2 | 1.0 |
| 10 | `primary_skill` | str | 0.0 | 11 | Web Development |
| 11 | `hourly_rate_usd` | float64 | 6.9 | 3,709 | 231.26 |
| 12 | `total_jobs_completed` | int64 | 0.0 | 61 | 24 |
| 13 | `job_success_rate` | float64 | 7.0 | 447 | 100.0 |
| 14 | `repeat_client_rate` | float64 | 6.2 | 555 | 0.327 |
| 15 | `avg_response_time_hrs` | float64 | 7.0 | 380 | 15.1 |
| 16 | `total_earnings_12m_usd` | int64 | 0.0 | 9,508 | 71463 |
| 17 | `success_score` | float64 | 0.0 | 473 | 82.2 |
| 18 | `churn_risk` | int64 | 0.0 | 2 | 0 |
| 19 | `earnings_tier` | str | 0.0 | 3 | High |

Numeric summary:

|                        |   count |      mean |      std |     min |      25% |       50% |      75% |       max |
|:-----------------------|--------:|----------:|---------:|--------:|---------:|----------:|---------:|----------:|
| age                    |   12000 |     36.13 |     8.92 |   21    |    28    |     36    |     44   |     51    |
| years_experience       |   12000 |      3.78 |     3.75 |    0    |     1.1  |      2.6  |      5.3 |     20    |
| num_skills             |   12000 |      9.51 |     3.45 |    4    |     7    |      9    |     12   |     15    |
| profile_completeness   |   12000 |     78.46 |    14.59 |   40    |    68.3  |     79.1  |     89.9 |    100    |
| has_portfolio          |   12000 |      0.7  |     0.46 |    0    |     0    |      1    |      1   |      1    |
| has_video_profile      |   12000 |      0.32 |     0.47 |    0    |     0    |      0    |      1   |      1    |
| has_certifications     |   11981 |      0.43 |     0.49 |    0    |     0    |      0    |      1   |      1    |
| hourly_rate_usd        |   11174 |    242.38 |    61.28 |   22.97 |   214.27 |    280    |    280   |    280    |
| total_jobs_completed   |   12000 |     30.32 |     8.28 |    9    |    25    |     29    |     35   |     70    |
| job_success_rate       |   11156 |     86    |     9.72 |   48.3  |    79.3  |     86.6  |     93.6 |    100    |
| repeat_client_rate     |   11254 |      0.33 |     0.1  |    0.05 |     0.26 |      0.33 |      0.4 |      0.68 |
| avg_response_time_hrs  |   11165 |     13.97 |     6.3  |    1.4  |     9.4  |     13    |     17.4 |     59.4  |
| total_earnings_12m_usd |   12000 | 131493    | 75855.6  | 2938    | 65875    | 117566    | 203315   | 245000    |
| success_score          |   12000 |     83.55 |    10.85 |   42.5  |    75.8  |     83.9  |     92.3 |     99    |
| churn_risk             |   12000 |      0.1  |     0.3  |    0    |     0    |      0    |      0   |      1    |

5 sample rows (seeded, text truncated):

| freelancer_id   |   age | gender   | country        |   years_experience |   num_skills |   profile_completeness |   has_portfolio |   has_video_profile |   has_certifications | primary_skill                 |   hourly_rate_usd |   total_jobs_completed |   job_success_rate |   repeat_client_rate |   avg_response_time_hrs |   total_earnings_12m_usd |   success_score |   churn_risk | earnings_tier   |
|:----------------|------:|:---------|:---------------|-------------------:|-------------:|-----------------------:|----------------:|--------------------:|---------------------:|:------------------------------|------------------:|-----------------------:|-------------------:|---------------------:|------------------------:|-------------------------:|----------------:|-------------:|:----------------|
| FL_004954       |    37 | Male     | United States  |                8.8 |           11 |                   87.6 |               1 |                   0 |                    1 | Content Writing / Copywriting |                   |                     44 |               80.2 |                0.499 |                     6.1 |                   245000 |            96.5 |            0 | High            |
| FL_011999       |    21 | Female   | United Kingdom |                1.3 |            7 |                  100   |               1 |                   0 |                    0 | AI & Machine Learning         |            280    |                     26 |                    |                0.43  |                    13   |                   144102 |            93.7 |            0 | High            |
| FL_011041       |    38 | Female   | United States  |                5.8 |            6 |                   77.5 |               1 |                   0 |                    0 | Digital Marketing             |            280    |                     41 |               79.7 |                0.291 |                    24.3 |                    37498 |            74.6 |            0 | Medium          |
| FL_007532       |    22 | Female   | India          |                3.3 |            7 |                   86.7 |               1 |                   0 |                    1 | Digital Marketing             |            274.44 |                     24 |               73.3 |                0.429 |                    24.2 |                    90905 |            94.9 |            0 | High            |
| FL_011966       |    22 | Male     | India          |                7.1 |            7 |                   73.7 |               1 |                   0 |                    1 | Web Development               |            280    |                     30 |               53.1 |                0.308 |                    19.2 |                    41617 |            70.6 |            0 | High            |
