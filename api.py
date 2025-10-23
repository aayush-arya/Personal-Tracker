from web_tracker import app as application

# The variable 'application' is the WSGI entry point Vercel requires.
# We import 'app' from your main file (web_tracker.py) and rename it to 'application'.

# Vercel now knows to run 'application' (which is your Flask app).
if __name__ == "__main__":
    application.run()