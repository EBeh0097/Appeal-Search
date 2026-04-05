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

## Local run
```bash
pip install -r requirements.txt
python -m playwright install chromium
streamlit run app.py
```

## Streamlit Community Cloud deployment
1. Push this folder to a **public GitHub repository**.
2. In Streamlit Community Cloud, click **Create app**.
3. Select the GitHub repo and branch.
4. Set the main file path to `app.py`.
5. In **Secrets**, add:
   ```toml
   OPENAI_API_KEY = "your-real-openai-key"
   ```
6. Deploy.

## Privacy
Do **not** commit your real API key to GitHub.
Use only Streamlit Community Cloud Secrets or a local `.streamlit/secrets.toml` file that stays out of version control.

## Suggested Git commands
```bash
git init
git add .
git commit -m "Initial Streamlit Medicare Appeals app"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```
