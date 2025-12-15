# 🔍 Evidence
## How NewbornHelper Identifies Real Pain Points

NewbornHelper is not based on personal anecdotes.

Its structure is derived from real discussions among Chinese parents in the U.S.,
where anxiety, over-purchasing, and safety confusion repeatedly surface.

---

## 📊 Data Source

- Platform: Xiaohongshu (Chinese community platform)
- Content type:
  - Newborn shopping lists
  - Product comparisons
  - “What should I buy?” questions
  - Postpartum regret and mistake sharing
- Audience:
  - First-time Chinese parents living in the U.S.
  - High information exposure, low decision certainty

The raw content was summarized into text data for analysis.

---

## 🧠 Method (Product-Oriented NLP)

Instead of building complex models, we asked a simpler and more relevant question:

> **What topics keep coming up across many different parents?**

Steps:
1. Extract recurring keywords from community summaries
2. Group them into interpretable concern categories
3. Translate those categories into user-facing pain points

The goal was not prediction accuracy,
but **decision relevance**.

---

## ☁️ Pain Point Word Cloud (Derived from Chinese Community Data)

The following word cloud visualizes the dominant concern clusters
identified from real discussions:

![Pain Point Word Cloud](./pain_point_wordcloud_en.png)

Key clusters include:
- Sleep Safety & Crib Setup
- Car Seats & Transportation
- Diapers & Feeding Supplies
- Overbuying Anxiety
- “Must-Have” vs “Do-Not-Buy” Confusion
- Lack of Postpartum Support

These are not edge cases.
They are **structural anxieties repeatedly expressed by new parents**.

---

## 🔗 From Pain Points to Product Structure

Each major cluster directly maps to a core module in NewbornHelper:

| Community Pain Point | NewbornHelper Module |
|---------------------|---------------------|
| Sleep safety confusion | checklist.md (Do-Not-Buy) |
| Car seat uncertainty | Must-Have list |
| Diaper / feeding overbuying | newborn_prep_plan.md |
| Checklist overload | Time-based preparation plan |
| “No one is helping” | helper_guide.md |

This ensures the project structure is driven by evidence,
not personal preference.

---

## 🧩 Why This Approach

We intentionally chose:
- Interpretable signals over black-box models
- Clear visuals over technical charts
- Product clarity over academic completeness

Because for exhausted new parents:

> **“I understand why this exists”  
> is more important than  
> “the model is complex.”**

---

## Summary

NewbornHelper is designed as a decision-support tool,
rooted in real community concerns,
and translated into actionable guidance.

If you recognize your own anxiety in these clusters,
this project was built for you.
