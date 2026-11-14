# Profile: asaniczka/upwork-job-postings-dataset-2024-50k-records

- source: https://www.kaggle.com/datasets/asaniczka/upwork-job-postings-dataset-2024-50k-records
- title: Upwork Job Postings Dataset 2024 (50K Records)
- subtitle: Real-time data collected over 2 weeks
- licence (from Kaggle metadata): **ODC Attribution License (ODC-By)**
- downloaded (UTC): 2026-11-14T21:53:22Z

## Files

| file | bytes |
|---|---|
| `dataset-metadata.json` | 2,324 |
| `upwork-jobs.csv` | 72,174,181 |

## Contents

### `upwork-jobs.csv`

- rows: **53,058**
- columns: **9**
- exact duplicate rows: 0

| # | column | dtype | null % | distinct | example |
|---|---|---|---|---|---|
| 0 | `title` | str | 0.0 | 47,077 | Experienced Media Buyer For Solar Pannel and Roofing installation companies. |
| 1 | `link` | str | 0.0 | 53,058 | https://www.upwork.com/jobs/Experienced-Media-Buyer-For-Solar-Pannel-and-Roofing-installation-companies_%7E0173dd044736… |
| 2 | `description` | str | 0.0 | 52,984 | We’re looking for a talented and hardworking ads manager to work with us and deliver consistent and high quality result… |
| 3 | `published_date` | str | 0.0 | 50,430 | 2024-02-17 09:09:54+00:00 |
| 4 | `is_hourly` | object | 15.5 | 2 | False |
| 5 | `hourly_low` | float64 | 56.7 | 85 | 10.0 |
| 6 | `hourly_high` | float64 | 58.2 | 158 | 30.0 |
| 7 | `budget` | float64 | 58.8 | 411 | 500.0 |
| 8 | `country` | str | 2.2 | 185 | United States |

Numeric summary:

|             |   count |   mean |      std |   min |   25% |   50% |   75% |     max |
|:------------|--------:|-------:|---------:|------:|------:|------:|------:|--------:|
| hourly_low  |   22956 |  17.47 |    18.23 |     3 |     8 |    15 |    20 | 500     |
| hourly_high |   22161 |  41.61 |    47.97 |     3 |    20 |    30 |    50 | 999     |
| budget      |   21873 | 746.26 | 10639.2  |     5 |    30 |   100 |   300 |   1e+06 |

5 sample rows (seeded, text truncated):

| title                                 | link                                                                                               | description                                                                                                              | published_date            | is_hourly   |   hourly_low |   hourly_high |   budget | country       |
|:--------------------------------------|:---------------------------------------------------------------------------------------------------|:-------------------------------------------------------------------------------------------------------------------------|:--------------------------|:------------|-------------:|--------------:|---------:|:--------------|
| English to Arabic translator          | https://www.upwork.com/jobs/English-Arabic-translator_%7E017521951d6dd82986?source=rss             | We are seeking a talented English to Arabic Translator to assist with translating various documents from English to Ara… | 2024-02-17 03:36:09+00:00 | False       |              |               |      120 | Bangladesh    |
| Enrollment Agent for USA tax-preparer | https://www.upwork.com/jobs/Enrollment-Agent-for-USA-tax-preparer_%7E0100236d5931bd58c3?source=rss | We are seeking an experienced Enrollment Agent who will be responsible for assisting with the enrollment process for ta… | 2024-02-19 14:56:41+00:00 | True        |            5 |             8 |          | United States |
| Bridge a ERC 20 Token to Solana       | https://www.upwork.com/jobs/Bridge-ERC-Token-Solana_%7E01c9429ff4d9490ae7?source=rss               | Analyze and understand the technical requirements for bridging an Ethereum token to Solana.Develop and test smart contr… | 2024-02-19 01:41:53+00:00 | False       |              |               |      100 | Thailand      |
| Full YouTube Automation Team          | https://www.upwork.com/jobs/Full-YouTube-Automation-Team_%7E017f33cd71bbf0146a?source=rss          | Hi! Thank you for checking out this job post. We are seeking a full YouTube Automation team that includes:- Script Writ… | 2024-02-19 23:09:22+00:00 | False       |              |               |       35 | Netherlands   |
| Accounting aid                        | https://www.upwork.com/jobs/Accounting-aid_%7E01b77d124af7e07dd6?source=rss                        | Assignment 1: Income Statement Assignment on Nike (Excel):FSAP Phase IPull the appropriate SEC Edgar files for your com… | 2024-02-18 00:23:38+00:00 | False       |              |               |       40 | United States |
