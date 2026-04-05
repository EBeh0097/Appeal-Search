# Medicare Appeals Streamlit App

This app wraps your Medicare Appeals scraper in a public Streamlit interface.

## What it does
- Accepts human input for:
  - H Contract #
  - Start Date
  - End Date
- Visits the Medicare Appeals search page
- Submits the search
- Collects all visible result pages
- Loads the results into a dataframe
- Calculates the two analysis metrics from your notebook
- Uses OpenAI for an optional plain-English summary when `OPENAI_API_KEY` is present in Streamlit secrets

