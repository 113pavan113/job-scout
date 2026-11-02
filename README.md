# job-scout

Scheduled job search: scrapes job boards, government vacancy pages and LinkedIn's
public job search, scores listings with keyword rules and Gemini, sends Telegram
alerts, and prepares applications.

Personal data (profile, CV, prompts, history) is kept in a separate private
repository and read at run time via `JOB_DATA_DIR`.
