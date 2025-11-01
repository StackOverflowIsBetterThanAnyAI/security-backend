# Security Backend

## Installation Guide

1. `pip install flask flask-cors python-dotenv werkzeug`

2. create a .env with admin credentials

## Usage Guide

1. User Authentication: Registrationand login. All new users receive a default user role.

2. Role Management: The admin has endpoints to upgrade or manage other users' roles.

3. Image Access Control: Ensures that the sensitive image endpoint is only accessible to users with the member role or better.

4. Raspberry Pi Integration: Acts as a proxy or service layer to fetch and serve the latest images from the connected Raspberry Pi Zero W.

## Frontend Repository

[Frontend Repository](https://github.com/StackOverflowIsBetterThanAnyAI/security-app)
