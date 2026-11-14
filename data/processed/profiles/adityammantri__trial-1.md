# Profile: adityammantri/trial-1

- source: https://www.kaggle.com/datasets/adityammantri/trial-1
- title: Fake-Job-Posting-Detection
- subtitle: A global dataset to detect and analyze real vs. fake online job postings.
- licence (from Kaggle metadata): **unknown**
- downloaded (UTC): 2026-11-14T21:55:58Z

## Files

| file | bytes |
|---|---|
| `dataset-metadata.json` | 1,524 |
| `preprocessed_unlabelled_data_bert.xlsx` | 183,429,934 |
| `processed_labeled_dataset_without_encoding.xlsx` | 23,629,039 |

## Contents

### `preprocessed_unlabelled_data_bert.xlsx`

- rows: **126,549**
- columns: **9**
- exact duplicate rows: 1,354

| # | column | dtype | null % | distinct | example |
|---|---|---|---|---|---|
| 0 | `title` | str | 0.0 | 73,270 | marketing coordinator |
| 1 | `location` | str | 0.0 | 8,981 | princeton, nj |
| 2 | `salary_range` | str | 0.0 | 10,814 | 20-17 |
| 3 | `company_profile` | str | 1.4 | 25,096 | corcoran sawyer smith |
| 4 | `job_desc` | str | 0.0 | 110,058 | job descriptiona leading real estate firm in new jersey is seeking an administrative marketing coordinator with some ex… |
| 5 | `skills_desc` | str | 95.9 | 4,802 | requirements: we are seeking a college or graduate student (can also be completed with school) with a focus in planning… |
| 6 | `employment_type` | str | 0.0 | 7 | fulltime |
| 7 | `No of reviews` | float64 | 3.5 | 684 | 20.0 |
| 8 | `text_input` | str | 0.0 | 125,195 | marketing coordinator / princeton, nj / 20-17 / corcoran sawyer smith / job descriptiona leading real estate firm in ne… |

Numeric summary:

|               |   count |   mean |   std |   min |   25% |   50% |   75% |   max |
|:--------------|--------:|-------:|------:|------:|------:|------:|------:|------:|
| No of reviews |  122160 |  14.62 |  85.9 |     1 |     3 |     4 |     8 |  9975 |

5 sample rows (seeded, text truncated):

| title                             | location                 | salary_range   | company_profile     | job_desc                                                                                                                 | skills_desc   | employment_type   |   No of reviews | text_input                                                                                                               |
|:----------------------------------|:-------------------------|:---------------|:--------------------|:-------------------------------------------------------------------------------------------------------------------------|:--------------|:------------------|----------------:|:-------------------------------------------------------------------------------------------------------------------------|
| scrum master                      | charleston, sc           | -              | apex systems        | job: 2024136 job description: apex systems, has an opportunity for a remote scrum master for one of our top dod clients… |               | fulltime          |               5 | scrum master / charleston, sc / - / apex systems / job: 2024136 job description: apex systems, has an opportunity for a… |
| delivery driver - earn extra cash | niagara falls, ny        | -              | simplyapply         | your time. your goals. what is doordash available in over 4,000 cities in the u.s, doordash connects local businesses a… |               | fulltime          |               1 | delivery driver - earn extra cash / niagara falls, ny / - / simplyapply / your time. your goals. what is doordash avail… |
| produce clerk part time           | canton, mi               | -              | bjs wholesale club  | join our team of more than 34,000 team members, supporting our members and communities in our club support center, 235 … |               | parttime          |               4 | produce clerk part time / canton, mi / - / bjs wholesale club / join our team of more than 34,000 team members, support… |
| billing specialist ii             | san antonio, tx          | -              | fis                 | position type full time type of hire experienced (relevant combo of work and education) education desired general equiv… |               | fulltime          |               8 | billing specialist ii / san antonio, tx / - / fis / position type full time type of hire experienced (relevant combo of… |
| program coordinator i             | wisconsin, united states | -              | centene corporation | you could be the one who changes everything for our 28 million members as a clinical professional on our medical manage… |               | fulltime          |               3 | program coordinator i / wisconsin, united states / - / centene corporation / you could be the one who changes everythin… |

### `processed_labeled_dataset_without_encoding.xlsx`

- rows: **54,391**
- columns: **10**
- exact duplicate rows: 3,238

| # | column | dtype | null % | distinct | example |
|---|---|---|---|---|---|
| 0 | `job_title` | str | 0.0 | 11,255 | mental health nurse |
| 1 | `location` | int64 | 0.0 | 4,727 | 4688 |
| 2 | `industry` | int64 | 0.0 | 1,400 | 649 |
| 3 | `salary_range` | str | 68.5 | 10,941 | 55016-100476 |
| 4 | `company_profile` | str | 15.4 | 12,070 | rivera and sons  established 2022 |
| 5 | `job_desc` | str | 6.5 | 28,410 | arm drive court sure vote earn 5000week immediate hiring contact now at david27gmailcom |
| 6 | `skills_desc` | str | 23.7 | 14,399 | basic knowledge in live no degree required flexible hours |
| 7 | `employment_type` | str | 28.6 | 11 | Internship |
| 8 | `fraudulent` | float64 | 19.0 | 2 | 1.0 |
| 9 | `text` | str | 0.0 | 34,193 | mental health nurse rivera and sons  established 2022 arm drive court sure vote earn 5000week immediate hiring contact … |

Numeric summary:

|            |   count |    mean |     std |   min |   25% |   50% |   75% |   max |
|:-----------|--------:|--------:|--------:|------:|------:|------:|------:|------:|
| location   |   54391 | 2171.31 | 1294.62 |     0 |  1166 |  2122 |  3170 |  4726 |
| industry   |   54391 |  882.29 |  431.46 |     0 |   524 |   805 |  1383 |  1399 |
| fraudulent |   44045 |    0.28 |    0.45 |     0 |     0 |     0 |     1 |     1 |

5 sample rows (seeded, text truncated):

| job_title                                 |   location |   industry | salary_range   | company_profile                                                                                                          | job_desc                                                                                                                 | skills_desc                                                                                                              | employment_type   |   fraudulent | text                                                                                                                     |
|:------------------------------------------|-----------:|-----------:|:---------------|:-------------------------------------------------------------------------------------------------------------------------|:-------------------------------------------------------------------------------------------------------------------------|:-------------------------------------------------------------------------------------------------------------------------|:------------------|-------------:|:-------------------------------------------------------------------------------------------------------------------------|
| asic physical design engineer             |       4245 |        438 | 60000-90000    |                                                                                                                          | job  physical design engineer contract  top level product development company  raleigh nc locationlooking for asic phys… | job title  physical design engineerexperience required  5 yearswork location  raleigh nc                                 | Contract          |            0 | asic physical design engineer  job  physical design engineer contract  top level product development company  raleigh n… |
| fullstack javascript software developer   |         66 |       1383 |                | franq is a pos development houseã we are part of a larger business called imposwe provide point of sale solutions to sm… | join a world class team thats committed to open sourcewe are seeking senior and midlevel developers to work on an excit… | mandatorythorough knowledge of javascript html5 and cssmore than 6 months commercial experience with a frontend develop… | Full-time         |            0 | fullstack javascript software developer franq is a pos development houseã we are part of a larger business called impos… |
| mobile applications  rd software engineer |       1174 |       1042 |                |                                                                                                                          | were looking for a motivated individual to work as mobile application developeryou will be responsible for developing a… | you must have at least 3 years working experience withã an excellent understanding of web development technologies html… |                   |            0 | mobile applications  rd software engineer  were looking for a motivated individual to work as mobile application develo… |
| customer service associate                |       4068 |        297 |                | novitex enterprise solutions formerly pitney bowes management services delivers innovative document and communications … | the customer service associate will be based in indianapolis in the right candidate will be an integral part of our tal… | minimum requirementshigh school diploma or equivalent ged requiredminimum of 6 months customer service experience requi… | Full-time         |            0 | customer service associate novitex enterprise solutions formerly pitney bowes management services delivers innovative d… |
| engineering geologist                     |       1478 |       1052 | 39422-86669    | griffith inc  established 2017                                                                                           | street meeting fine center earn 5000week immediate hiring contact now at angelaburchhotmailcom                           | basic knowledge in learn no degree required flexible hours                                                               | Full-Time         |            1 | engineering geologist griffith inc  established 2017 street meeting fine center earn 5000week immediate hiring contact … |
