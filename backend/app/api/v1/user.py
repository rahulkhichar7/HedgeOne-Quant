from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter() #router helps split the api into moduls

@router.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>FastAPI Home</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: #f9f9f9;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                color: #333;
                text-align: center;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 20px;
                box-shadow: 0 8px 30px rgba(0, 0, 0, 0.1);
                max-width: 500px;
            }
            h1 {
                font-size: 2.5em;
                margin-bottom: 15px;
                color: #007bff;
            }
            p {
                font-size: 1.2em;
                line-height: 1.5;
                margin-bottom: 25px;
                color: #555;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Welcome to FastAPI 🚀</h1>
            <p>Explore and build interactive APIs with Python in a beautiful interface.</p>
        </div>
    </body>
    </html>
    """
