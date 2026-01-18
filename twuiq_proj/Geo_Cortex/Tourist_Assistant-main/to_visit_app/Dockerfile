# Use Python as the base image
FROM python:3.12.4

# Set the working directory inside the container
WORKDIR /app

# Copy the application files into the container
COPY . /app

# Install required dependencies
RUN pip install --no-cache-dir fastapi uvicorn docker python-multipart  python-jose[cryptography] passlib bcrypt SQLAlchemy sqlmodel

# Expose the FastAPI port
EXPOSE 8000

# Command to run the FastAPI app
CMD ["uvicorn", "main:app","--host", "0.0.0.0", "--port", "8000","--reload"]
