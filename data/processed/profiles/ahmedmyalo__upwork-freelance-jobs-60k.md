# Profile: ahmedmyalo/upwork-freelance-jobs-60k

- source: https://www.kaggle.com/datasets/ahmedmyalo/upwork-freelance-jobs-60k
- title: Upwork freelance jobs (+60k)
- subtitle: +60K various jobs scrapped from Upwork site (this year 2023)
- licence (from Kaggle metadata): **apache-2.0**
- downloaded (UTC): 2026-11-14T21:54:12Z

## Files

| file | bytes |
|---|---|
| `Contact.rtf` | 1,162 |
| `dataset-metadata.json` | 6,983 |
| `Features (columns) description.docx` | 17,869 |
| `Final_Upwork_Dataset.csv` | 92,485,880 |
| `Final_Upwork_Dataset.xlsx` | 32,826,702 |
| `Introduction to the Data.docx` | 15,971 |

## Contents

### `Contact.rtf` (non-tabular, 1,162 bytes)

```text
{\rtf1\ansi\ansicpg1252\deff0\nouicompat\deflang1033{\fonttbl{\f0\froman\fcharset0 inherit;}{\f1\fswiss\fprq2\fcharset0 Calibri;}{\f2\fnil\fcharset0 Calibri;}}
{\colortbl ;\red60\green64\blue67;\red0\green0\blue255;\red32\green33\blue36;\red255\green255\blue255;}
{\*\generator Riched20 10.0.22621}\viewkind4\uc1 
\pard\cbpat4\widctlpar\sl330\slmult0\cf1\f0\fs21\lang2057 If you have any questions or comments about the dataset, please do not hesitate to reach out to me:\par
\par
LinkedIn:\~ {\cf0\f1\fs22\lang1033{\field{\*\fldinst{HYPERLINK https://www.linkedin.com/in/ahmed-mayalou-043885267/ }}{\fldrslt{https://www.linkedin.com/in/ahmed-mayalou-043885267/\ul0\cf0}}}}\cf0\f1\fs22\lang1033\par
{\f0\fs21\lang2057{\field{\*\fldinst{HYPERLINK https://www.kaggle.com/ahmedmyalo/ }}{\fldrslt{https://www.kaggle.com/ahmedmyalo/\ul0\cf0}}}}\cf3\ul\f0\fs21\lang2057  \par
\cf1\ulnone You can also reach me via email at:\~{\cf0\f1\fs22\lang1033{\field{\*\fldinst{HYPERLINK "mailto:ahmedmyalo00@gmail.com" }}{\fldrslt{\ul\cf2\cf3\ul\f0\fs21\lang2057 ahmedmyalo00@gmail.com}}}}\cf3\ul\f0\fs21\par

\pard\sa200\sl276\slmult1\cf0\ulnone\f2\fs22\lang9\par
}
```

### `Features (columns) description.docx` (docx, 17,869 bytes)

```text
The Dataset 📊
now let's interpret the dataset after I cleaned the mess…Interpretation of Feature columns:-
Job Title: Specifies the nature of the job. It aids potential applicants in quickly understanding the role that client needs.
Job_URL: A direct pathway to the full job details, ensuring authenticity and providing additional specifics (sometimes it not works because the job was deleted from the site).
EX_level_demand: Describes the skill tier desired. Helps candidates evaluate if they are a fit for the job. (there's 3 tiers on the site: "Entry level &amp; Intermediate &amp; Expert")
Time_Limitation: Indicates the roughly time frame the client demands for the job, assisting freelancers in managing their schedules. (they's a few varieties not much)
Search_Keyword: the keyword I've used in search bar to get that row result. I've used (3D &amp; Data science &amp; Developer &amp; Marketing) but I didn't scrap these fields with the same quantity.
Posted_from: that's the time between the client posted the job and scrapping time that job.
Description: the full description of the job which client wrote.
Category_1 to Category_9: These columns specify categories of skills that the client wrote as a relevant to the job. Each category column is paired with a corresponding URL ("CategoryX_URL_search") which leads to a search page for requiring the specified skill.
Category1_URL_search to Category9_URL_search: Direct links to related skills/categories give insights into potential prerequisites for the job.
highlight: it's an indicator about this job related to.
*So, while "Highlight" is about the visual or attention-grabbing aspect of a job post, "Category" relates to the organizational system that sorts jobs into different fields or types of work. In your dataset, each job will belong to one category (showing the field of work) but may or may not be highlighted, depending on whether the client has opted for that feature to make their post more noticeable.as a freelancer: focus on the "Category" trends for search more than "Highlight"
Applicants_Num: number of the freelancers who applied proposal for that job yet. A high number might deter some from applying.
Payment_Situation: the client activated and verified his payment card account on the site or not. (verifying shows that the client is serious even he didn't spend any money yet on the site).
Enterprise_client: it typically refers to a large corporation or organization that uses the Upwork platform to source and manage freelancers and agencies for various projects.The average Upwork Enterprise client has:10x MORE JOBS POSTED15x MORE MONEY SPENT50% MORE WORK DONEsome of them spent millions on Upwork platform on the freelancers ^_^
Freelancers_Num: number of freelancers that the client needs for the job (usually it's just one).
Spent($): Reflects how much the client spent on the site since he joined. (the more client spends; the more his job is attractive cuz he's usually serious and generous).
Client_Country: Knowledge of client location can influence decisions based on time zones or cultural familiarity.
Connects_Num: connects are the currency of the site; the freelancers buy every 10 connects for 1.5$ . so the more job costs the less freelancers applying for it.(the job costs 1, 2, 4, 6 or 8 connects)
New_Connects_Num: currently the site doubled the connects for the jobs, so now it's (2, 4, 8, 12, 16)
Rating: A reflection of the client's reputation, influencing trust and the decision to apply. (be careful from the number of feedbacks if it's just 1 feedback with 5 stars rating maybe it's not real honest feedback)
Feedback_Num: number of feedbacks that previous freelancers gave to the client. the more it is the more honesty of feedbacks.
Payment_type: there's 2 types that clients paying for the project "Fixed-price" for the whole project at once &amp; "Hourly" it counts every working hour and pay depends on the price per hour.
Job_Cost: it's for "Fixed-price" projects; The projected
```

### `Final_Upwork_Dataset.csv`

- rows: **63,950**
- columns: **41**
- exact duplicate rows: 169

| # | column | dtype | null % | distinct | example |
|---|---|---|---|---|---|
| 0 | `Job Title` | str | 0.0 | 54,907 | Power bi specialist freelance |
| 1 | `Job_URL` | str | 0.0 | 61,560 | https://www.upwork.com/jobs/Power-specialist-freelance_~011e995e98fafa73e6/ |
| 2 | `EX_level_demand` | str | 11.0 | 3 | Expert |
| 3 | `Time_Limitation` | str | 64.0 | 16 | 3 to 6 months, Less than 30 hrs/week |
| 4 | `Search_Keyword` | str | 0.0 | 4 | Data_science |
| 5 | `Posted_from` | str | 0.1 | 106 | 5 minutes ago |
| 6 | `Description` | str | 0.0 | 59,278 | Already data pooled and designed. Need to refine add or separate tab |
| 7 | `Category1_URL_search` | str | 0.7 | 2,239 | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626729515892736 |
| 8 | `Category_1` | str | 0.7 | 2,239 | Data Analysis |
| 9 | `highlight` | str | 21.6 | 329 | data |
| 10 | `Category2_URL_search` | str | 6.4 | 2,716 | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1052162208890146823 |
| 11 | `Category_2` | str | 6.4 | 2,718 | Data Visualization |
| 12 | `Category3_URL_search` | str | 14.0 | 2,895 | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626759018627072 |
| 13 | `Category_3` | str | 14.0 | 2,897 | Microsoft Power BI |
| 14 | `Category4_URL_search` | str | 25.7 | 2,839 | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626782364123136 |
| 15 | `Category_4` | str | 25.7 | 2,841 | SQL |
| 16 | `Category5_URL_search` | str | 38.1 | 2,723 | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626759027015680 |
| 17 | `Category_5` | str | 38.1 | 2,726 | Microsoft PowerPoint |
| 18 | `Category6_URL_search` | str | 51.0 | 2,530 | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=996364628025274386 |
| 19 | `Category_6` | str | 51.0 | 2,533 | Python |
| 20 | `Category7_URL_search` | str | 60.6 | 2,353 | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626712596070400 |
| 21 | `Category_7` | str | 60.6 | 2,355 | Analytics |
| 22 | `Category8_URL_search` | str | 68.0 | 2,222 | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626793785212928 |
| 23 | `Category_8` | str | 68.0 | 2,224 | Visualization |
| 24 | `Category9_URL_search` | str | 74.2 | 2,069 | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626712596070400 |
| 25 | `Category_9` | str | 74.2 | 2,070 | Analytics |
| 26 | `Applicants_Num` | str | 0.0 | 6 | Less than 5 |
| 27 | `Payment_Situation` | str | 0.0 | 2 | Payment unverified |
| 28 | `Enterprise_Client` | str | 99.9 | 1 | Enterprise |
| 29 | `Freelancers_Num` | int64 | 0.0 | 35 | 1 |
| 30 | `Spent($)` | float64 | 2.6 | 64 | 0.0 |
| 31 | `Client_Country` | str | 0.2 | 187 | United States |
| 32 | `Connects_Num` | float64 | 0.0 | 5 | 6.0 |
| 33 | `New_Connects_Num` | float64 | 0.0 | 5 | 12.0 |
| 34 | `Rating` | float64 | 52.2 | 13,994 | 5.0 |
| 35 | `Feedback_Num` | float64 | 0.0 | 547 | 0.0 |
| 36 | `Payment_type` | str | 0.0 | 2 | Fixed-price |
| 37 | `Job_Cost` | str | 68.5 | 423 | $2,500  |
| 38 | `Hourly_Rate` | str | 58.5 | 1,886 | $40.00  |
| 39 | `Start_rate` | str | 0.0 | 191 | 0 |
| 40 | `End_rate` | str | 59.4 | 255 | $100.00  |

Numeric summary:

|                  |   count |     mean |       std |   min |   25% |   50% |   75% |       max |
|:-----------------|--------:|---------:|----------:|------:|------:|------:|------:|----------:|
| Freelancers_Num  |   63950 |     1.14 |      2.39 |     0 |  1    |  1    |     1 |    99     |
| Spent($)         |   62304 | 29997.9  | 392651    |     0 |  0    | 80    |  4000 |     7e+07 |
| Connects_Num     |   63949 |     4.51 |      2.1  |     1 |  2    |  4    |     6 |     8     |
| New_Connects_Num |   63949 |     9.01 |      4.2  |     2 |  4    |  8    |    12 |    16     |
| Rating           |   30593 |     4.82 |      0.42 |     1 |  4.84 |  4.98 |     5 |     5     |
| Feedback_Num     |   63949 |    21    |    180.45 |     0 |  0    |  0    |    10 | 12541     |

5 sample rows (seeded, text truncated):

| Job Title                                                 | Job_URL                                                                                                              | EX_level_demand   | Time_Limitation                          | Search_Keyword   | Posted_from   | Description                                                                                                              | Category1_URL_search                                                          | Category_1   | highlight   | Category2_URL_search                                                          | Category_2       | Category3_URL_search                                                          | Category_3                | Category4_URL_search                                                          | Category_4   | Category5_URL_search                                                          | Category_5   | Category6_URL_search                                                          | Category_6            | Category7_URL_search   | Category_7   | Category8_URL_search   | Category_8   | Category9_URL_search   | Category_9   | Applicants_Num   | Payment_Situation   | Enterprise_Client   |   Freelancers_Num |   Spent($) | Client_Country   |   Connects_Num |   New_Connects_Num |   Rating |   Feedback_Num | Payment_type   | Job_Cost   | Hourly_Rate   | Start_rate   | End_rate   |
|:----------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------|:------------------|:-----------------------------------------|:-----------------|:--------------|:-------------------------------------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------|:-------------|:------------|:------------------------------------------------------------------------------|:-----------------|:------------------------------------------------------------------------------|:--------------------------|:------------------------------------------------------------------------------|:-------------|:------------------------------------------------------------------------------|:-------------|:------------------------------------------------------------------------------|:----------------------|:-----------------------|:-------------|:-----------------------|:-------------|:-----------------------|:-------------|:-----------------|:--------------------|:--------------------|------------------:|-----------:|:-----------------|---------------:|-------------------:|---------:|---------------:|:---------------|:-----------|:--------------|:-------------|:-----------|
| Optimize google ads campaign                              | https://www.upwork.com/jobs/Optimize-google-ads-campaign_~014efe14a883f792e7/                                        | Expert            | Less than 1 month, Less than 30 hrs/week | Marketing        | 3 days ago    | I have campaign set up on Google ads for our website successful dating.net. The campaign is to generate a lead, and the… | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626741817786368 | Google Ads   |             | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626741842952192 | Google Analytics | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626770318082048 | Pay Per Click Advertising |                                                                               |              |                                                                               |              |                                                                               |                       |                        |              |                        |              |                        |              | 20 to 50         | Payment verified    |                     |                 1 |      10000 | Netherlands      |              2 |                  4 |  4.92337 |             26 | Hourly         |            | $18-$55       | $18          | $55        |
| Complete Woocommerce/WP Website                           | https://www.upwork.com/jobs/Complete-Woocommerce-Website_~0173e78d01195f5abb/                                        | Expert            |                                          | Developer        | 3 days ago    | We have a 70% complete website, the developer became ill and we need someone to help us get it finished.  It's a Woocom… | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1052162208999198724 | WordPress    | developer   | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626796331155456 | WooCommerce      | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=996364628025274385  | PHP                       | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626728794472448 | CSS          | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626745110315008 | HTML         |                                                                               |                       |                        |              |                        |              |                        |              | 50+              | Payment verified    |                     |                 1 |      90000 | United Kingdom   |              8 |                 16 |  4.66992 |            103 | Fixed-price    | $1,200     |               | 0            |            |
| Tableau Archiving Expertise                               | https://www.upwork.com/jobs/Tableau-Archiving-Expertise_~01a9a19083864983eb/                                         | Expert            |                                          | Data_science     | 14 days ago   | We need some expertise to help us design our archiving strategy, including how we transfer data to Tableau, incremental… | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626730287644672 | Data Mining  | data        | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626729515892736 | Data Analysis    | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626784704544768 | Tableau                   | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626782364123136 | SQL          | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626736444882944 | ETL          | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626721978728448 | Business Intelligence |                        |              |                        |              |                        |              | 10 to 15         | Payment verified    |                     |                 1 |        100 | United States    |              4 |                  8 |          |              0 | Fixed-price    | $150       |               | 0            |            |
| Basic Java Project                                        | https://www.upwork.com/jobs/Basic-Java-Project_~016d3b3cff065f2de5/                                                  | Expert            |                                          | Developer        | 2 days ago    | You will complete a basic Java project.  The project is in Three parts but they all use the same basic project which yo… | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=996364628025274382  | Java         |             |                                                                               |                  |                                                                               |                           |                                                                               |              |                                                                               |              |                                                                               |                       |                        |              |                        |              |                        |              | 50+              | Payment verified    |                     |                 1 |        100 | Canada           |              2 |                  4 |  5       |              4 | Fixed-price    | $35        |               | 0            |            |
| Develop leverage/margin trading engine using current code | https://www.upwork.com/jobs/span-Develop-span-leverage-margin-trading-engine-using-current-code_~01458fb1a5df62ed3c/ | Expert            |                                          | Developer        | 1 day ago     | We would like to have some developments on the current code which is a scalable simple trading platform with simple fun… | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=1031626741679374336 | Golang       | Develop     | https://www.upwork.com/nx/jobs/search/?ontology_skill_uid=996364628025274382  | Java             |                                                                               |                           |                                                                               |              |                                                                               |              |                                                                               |                       |                        |              |                        |              |                        |              | 5 to 10          | Payment verified    |                     |                 1 |      30000 | Turkey           |              6 |                 12 |  4.9968  |             64 | Fixed-price    | $1,000     |               | 0            |            |

### `Final_Upwork_Dataset.xlsx`

Same table as `Final_Upwork_Dataset.csv`; skipped.

### `Introduction to the Data.docx` (docx, 15,971 bytes)

```text
Introduction…🫡
As a freelancer (Top_rated on Upwork) I was always looking for dataset about freelance jobs so…
I'm excited to introduce my newly curated dataset which I've scrapped, cleaned and organised beside keeping most info which maybe helpful; encompassing freelance job postings from Upwork (most popular freelance site), spanning February and March 2023. This treasure trove consists of +60,000 job, diversely focused on three thriving sectors: 3D (Art &amp; Architecture), programming, and marketing.
I intend to analyse it and maybe do some ML on it too later btw..
so, Why should you delve into this dataset? 🥰
Broad Spectrum: Capture insights across 3D design, coding projects, and marketing campaigns, showcasing the diversity of freelance opportunities.
Cleaned for Precision: We understand the value of clean data. Our dataset is meticulously processed, ensuring you can dive straight into the analysis.
Pulse of the Current Market: This dataset provides a snapshot of the current freelancing landscape, helping you derive timely and relevant insights.
If you've been searching for a comprehensive, clean, and contemporary dataset that covers the buzzing world of freelancing, this is it. Let's uncover the patterns, trends, and insights that define the freelance realm in 2023 together.
Why Upwork? 🤩
Upwork is a leading freelance platform with global reach, offering a diverse range of job categories. Its rigorous verification and feedback systems ensure data quality, making it an ideal source to gauge freelance market trends.

If you have any questions or comments about the dataset, please do not hesitate to reach out to me:

LinkedIn:  https://www.linkedin.com/in/ahmed-mayalou-043885267/
https://www.kaggle.com/ahmedmyalo/ 
You can also reach me via email at: ahmedmyalo00@gmail.com
```
