# Profile: asaniczka/all-jobs-on-upwork-200k-plus

- source: https://www.kaggle.com/datasets/asaniczka/all-jobs-on-upwork-200k-plus
- title: All Upwork Job Postings - Monthly Tracker
- subtitle: All job postings on Upwork collected minute by minute (200k plus)
- licence (from Kaggle metadata): **ODC Attribution License (ODC-By)**
- downloaded (UTC): 2026-11-14T21:53:50Z

## Files

| file | bytes |
|---|---|
| `all_upwork_jobs_2024-02-07-2024-03-24.csv` | 50,577,682 |
| `all_upwork_jobs_2024-03-24-2024-05-21.csv` | 53,782,241 |
| `all_upwork_jobs_2024-05-21-2024-07-25.csv` | 56,869,517 |
| `dataset-metadata.json` | 1,632 |

## Contents

### `all_upwork_jobs_2024-02-07-2024-03-24.csv`

- rows: **244,828**
- columns: **8**
- exact duplicate rows: 0

| # | column | dtype | null % | distinct | example |
|---|---|---|---|---|---|
| 0 | `title` | str | 0.0 | 205,470 | Experienced Media Buyer For Solar Pannel and Roofing installation companies. |
| 1 | `link` | str | 0.0 | 244,827 | https://www.upwork.com/jobs/Experienced-Media-Buyer-For-Solar-Pannel-and-Roofing-installation-companies_%7E0173dd044736… |
| 2 | `published_date` | str | 0.0 | 233,640 | 2024-02-17 09:09:54+00:00 |
| 3 | `is_hourly` | bool | 0.0 | 2 | False |
| 4 | `hourly_low` | float64 | 58.2 | 114 | 10.0 |
| 5 | `hourly_high` | float64 | 59.7 | 227 | 30.0 |
| 6 | `budget` | float64 | 57.6 | 768 | 500.0 |
| 7 | `country` | str | 2.1 | 212 | United States |

Numeric summary:

|             |   count |   mean |      std |   min |   25% |   50% |   75% |     max |
|:------------|--------:|-------:|---------:|------:|------:|------:|------:|--------:|
| hourly_low  |  102422 |  17.34 |    18.14 |     3 |     8 |    15 |    20 | 998     |
| hourly_high |   98775 |  41.97 |    47.85 |     3 |    20 |    30 |    50 | 999     |
| budget      |  103891 | 911.47 | 15729.7  |     5 |    25 |   100 |   300 |   1e+06 |

5 sample rows (seeded, text truncated):

| title                                                 | link                                                                                                               | published_date            | is_hourly   |   hourly_low |   hourly_high |   budget | country       |
|:------------------------------------------------------|:-------------------------------------------------------------------------------------------------------------------|:--------------------------|:------------|-------------:|--------------:|---------:|:--------------|
| Kajabi Expert and Tech Support                        | https://www.upwork.com/jobs/Kajabi-Expert-and-Tech-Support_%7E01337e16dc7b159898?source=rss                        | 2024-03-15 07:48:52+00:00 | True        |           10 |            25 |          | Vietnam       |
| Social media Marketing and General Virtual Assistance | https://www.upwork.com/jobs/Social-media-Marketing-and-General-Virtual-Assistance_%7E01dd2e38f75ef40027?source=rss | 2024-02-23 16:51:17+00:00 | True        |              |               |          | United States |
| Basic Graphic Designing work                          | https://www.upwork.com/jobs/Basic-Graphic-Designing-work_%7E01b2a01e5ab880c95a?source=rss                          | 2024-02-24 09:10:02+00:00 | True        |              |               |          | India         |
| CodeIgniter Script Customize                          | https://www.upwork.com/jobs/CodeIgniter-Script-Customize_%7E01b5cfdae21ed9304e?source=rss                          | 2024-02-14 06:59:47+00:00 | False       |              |               |       50 | India         |
| Wordpress website re-design and development           | https://www.upwork.com/jobs/Wordpress-website-design-and-development_%7E010b1cc906b69b87c2?source=rss              | 2024-03-04 13:18:39+00:00 | False       |              |               |    16000 | Norway        |

### `all_upwork_jobs_2024-03-24-2024-05-21.csv`

- rows: **283,000**
- columns: **8**
- exact duplicate rows: 66

| # | column | dtype | null % | distinct | example |
|---|---|---|---|---|---|
| 0 | `title` | str | 0.0 | 236,707 | Real Estate Acquisitions Specialist (Virtual Assistant) |
| 1 | `link` | str | 0.0 | 282,934 | https://www.upwork.com/jobs/Real-Estate-Acquisitions-Specialist-Virtual-Assistant_%7E01ed2a6e0ad5dd7a3c?source=rss |
| 2 | `published_date` | str | 0.0 | 270,778 | 2024-05-20 19:14:32+00 |
| 3 | `is_hourly` | object | 16.2 | 2 | True |
| 4 | `hourly_low` | float64 | 58.9 | 118 | 4.0 |
| 5 | `hourly_high` | float64 | 60.4 | 209 | 6.0 |
| 6 | `budget` | float64 | 57.3 | 819 | 50.0 |
| 7 | `country` | str | 2.5 | 217 | United States |

Numeric summary:

|             |   count |   mean |      std |   min |   25% |   50% |   75% |     max |
|:------------|--------:|-------:|---------:|------:|------:|------:|------:|--------:|
| hourly_low  |  116288 |  16.8  |    16.02 |     3 |     7 |    15 |    20 | 950     |
| hourly_high |  112102 |  40.58 |    44.39 |     3 |    20 |    30 |    50 | 999     |
| budget      |  120838 | 912.62 | 16914.6  |     5 |    30 |   100 |   300 |   1e+06 |

5 sample rows (seeded, text truncated):

| title                                                        | link                                                                                                                   | published_date         | is_hourly   |   hourly_low |   hourly_high |   budget | country        |
|:-------------------------------------------------------------|:-----------------------------------------------------------------------------------------------------------------------|:-----------------------|:------------|-------------:|--------------:|---------:|:---------------|
| Shopify Website Designer and Developer                       | https://www.upwork.com/jobs/Shopify-Website-Designer-and-Developer_%7E011ef539754b203db4?source=rss                    | 2024-04-24 18:55:42+00 | True        |            5 |            10 |          | United Kingdom |
| Animated Video of Square App Rolling Across Different Cities | https://www.upwork.com/jobs/Animated-Video-Square-App-Rolling-Across-Different-Cities_%7E01a490d20a419e5670?source=rss | 2024-05-10 03:14:15+00 | True        |           15 |            35 |          | Australia      |
| Wordpress / Woocommerce Website Update                       | https://www.upwork.com/jobs/Wordpress-Woocommerce-Website-Update_%7E0113bf82e1283ee2e4?source=rss                      | 2024-04-05 22:58:14+00 | True        |            5 |            30 |          | United States  |
| Operations Manager                                           | https://www.upwork.com/jobs/Operations-Manager_%7E01f96df7d75b183c67?source=rss                                        | 2024-04-29 13:12:28+00 |             |              |               |          | United States  |
| Arabic Female Spokesperson for Product Video                 | https://www.upwork.com/jobs/Arabic-Female-Spokesperson-for-Product-Video_%7E0113ecb58929210ad6?source=rss              | 2024-04-19 11:03:28+00 | False       |              |               |      150 | Turkey         |

### `all_upwork_jobs_2024-05-21-2024-07-25.csv`

- rows: **298,500**
- columns: **8**
- exact duplicate rows: 93,012

| # | column | dtype | null % | distinct | example |
|---|---|---|---|---|---|
| 0 | `title` | str | 0.0 | 177,408 | Shopify Template Change + Analytics setup |
| 1 | `link` | str | 0.0 | 205,488 | https://www.upwork.com/jobs/Shopify-Template-Change-Analytics-setup_%7E01a6bb8a7618b70426?source=rss |
| 2 | `published_date` | str | 0.0 | 198,230 | 2024-05-20 19:34:50+00 |
| 3 | `is_hourly` | object | 16.4 | 2 | True |
| 4 | `hourly_low` | float64 | 59.2 | 119 | 20.0 |
| 5 | `hourly_high` | float64 | 60.6 | 210 | 75.0 |
| 6 | `budget` | float64 | 57.2 | 669 | 1500.0 |
| 7 | `country` | str | 3.1 | 327 | Denmark |

Numeric summary:

|             |   count |    mean |      std |   min |   25% |   50% |   75% |     max |
|:------------|--------:|--------:|---------:|------:|------:|------:|------:|--------:|
| hourly_low  |  121883 |   16.97 |    17.51 |     3 |     7 |    14 |    20 | 900     |
| hourly_high |  117601 |   40.62 |    43.81 |     3 |    20 |    30 |    50 | 999     |
| budget      |  127636 | 1149.07 | 19650.8  |     5 |    30 |   100 |   300 |   1e+06 |

5 sample rows (seeded, text truncated):

| title                                                                                    | link                                                                                                                     | published_date         | is_hourly   |   hourly_low |   hourly_high |   budget | country       |
|:-----------------------------------------------------------------------------------------|:-------------------------------------------------------------------------------------------------------------------------|:-----------------------|:------------|-------------:|--------------:|---------:|:--------------|
| Seeking Cybersecurity Expert to Identify Vulnerabilities on a Booking Website            | https://www.upwork.com/jobs/Seeking-Cybersecurity-Expert-Identify-Vulnerabilities-Booking-Website_%7E016ea22f7cdabe4acd… | 2024-06-15 07:30:24+00 | False       |              |               |     1000 | Algeria       |
| AI-based Animated (Video) Zoom Wallpaper: Mission Control Office looking to a launch pad | https://www.upwork.com/jobs/based-Animated-Video-Zoom-Wallpaper-Mission-Control-Office-looking-launch-pad_%7E01f3067f47… | 2024-05-28 19:15:47+00 | True        |           18 |            35 |          | Germany       |
| High-retention scriptwriter for YouTube                                                  | https://www.upwork.com/jobs/High-retention-scriptwriter-for-YouTube_%7E018108408674e2b07c?source=rss                     | 2024-06-26 21:44:37+00 | False       |              |               |      200 | United States |
| Client manager medical billing                                                           | https://www.upwork.com/jobs/Client-manager-medical-billing_%7E01f41fcafac8f57345?source=rss                              | 2024-05-29 16:40:12+00 | True        |           10 |            35 |          | United States |
| Saas landing page with dark theme                                                        | https://www.upwork.com/jobs/Saas-landing-page-with-dark-theme_%7E0172f5964ae4624f49?source=rss                           | 2024-07-23 11:25:23+00 | False       |              |               |      400 | Pakistan      |
