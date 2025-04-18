from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pandas as pd
import io
import json
import os
from datetime import datetime
import uuid
from typing import List, Dict, Any, Optional
import numpy as np
import plotly.express as px
import plotly.io as pio
import plotly.utils as plt_utils
from pydantic import BaseModel

# Create uploads directory if it doesn't exist
os.makedirs("uploads", exist_ok=True)
os.makedirs("upload_history", exist_ok=True)

HISTORY_FILE = "upload_history/history.json"

# Initialize history file if it doesn't exist
if not os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "w") as f:
        json.dump([], f)

app = FastAPI(title="CSV Analytics API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ColumnStats(BaseModel):
    name: str
    dtype: str
    count: int
    missing: int
    missing_pct: float
    unique: int
    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    
class FileUploadResponse(BaseModel):
    file_id: str
    filename: str
    upload_time: str
    size: str
    column_count: int
    row_count: int
    
class CSVMetadata(BaseModel):
    file_id: str
    filename: str
    upload_time: str
    size: str
    column_count: int
    row_count: int
    columns: List[str]
    dtypes: Dict[str, str]
    preview: List[Dict[str, Any]]

def load_upload_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_upload_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)

@app.get("/")
async def root():
    return {"message": "CSV Analytics API"}

@app.post("/upload", response_model=FileUploadResponse)
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")
    
    file_id = str(uuid.uuid4())
    file_location = f"uploads/{file_id}.csv"
    
    try:
        # Read file contents
        contents = await file.read()
        with open(file_location, "wb") as f:
            f.write(contents)
        
        # Try different encodings to read the CSV file
        encodings_to_try = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
        df = None
        
        for encoding in encodings_to_try:
            try:
                df = pd.read_csv(io.BytesIO(contents), encoding=encoding)
                # If successful, save the encoding for future use
                with open(f"uploads/{file_id}.encoding", "w") as f:
                    f.write(encoding)
                break
            except UnicodeDecodeError:
                continue
        
        if df is None:
            raise HTTPException(status_code=400, detail="Unable to decode CSV file. Please check the file encoding.")
            
        row_count = len(df)
        column_count = len(df.columns)
        file_size = f"{len(contents) / 1024:.2f} KB"
        
        # Get upload history and add new entry
        history = load_upload_history()
        upload_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        new_entry = {
            "file_id": file_id,
            "filename": file.filename,
            "upload_time": upload_time,
            "size": file_size,
            "column_count": column_count,
            "row_count": row_count
        }
        
        history.append(new_entry)
        save_upload_history(history)
        
        return FileUploadResponse(**new_entry)
        
    except Exception as e:
        if os.path.exists(file_location):
            os.remove(file_location)
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

@app.get("/files", response_model=List[FileUploadResponse])
async def get_uploaded_files():
    history = load_upload_history()
    return history

@app.get("/files/{file_id}", response_model=CSVMetadata)
async def get_file_metadata(file_id: str):
    history = load_upload_history()
    file_info = next((item for item in history if item["file_id"] == file_id), None)
    
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_path = f"uploads/{file_id}.csv"
    encoding_path = f"uploads/{file_id}.encoding"
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="CSV file not found on server")
    
    try:
        # Read the encoding if available
        encoding = 'utf-8'  # Default
        if os.path.exists(encoding_path):
            with open(encoding_path, 'r') as f:
                encoding = f.read().strip()
        
        df = pd.read_csv(file_path, encoding=encoding)
        
        # Get column types
        dtypes = {col: str(dtype) for col, dtype in df.dtypes.items()}
        
        # Prepare preview data (first 10 rows)
        preview = df.head(10).replace({np.nan: None}).to_dict(orient="records")
        
        metadata = {
            **file_info,
            "columns": df.columns.tolist(),
            "dtypes": dtypes,
            "preview": preview
        }
        
        return CSVMetadata(**metadata)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

@app.get("/files/{file_id}/stats")
async def get_file_stats(file_id: str):
    history = load_upload_history()
    file_info = next((item for item in history if item["file_id"] == file_id), None)
    
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_path = f"uploads/{file_id}.csv"
    encoding_path = f"uploads/{file_id}.encoding"
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="CSV file not found on server")
    
    try:
        # Read the encoding if available
        encoding = 'utf-8'  # Default
        if os.path.exists(encoding_path):
            with open(encoding_path, 'r') as f:
                encoding = f.read().strip()
        
        df = pd.read_csv(file_path, encoding=encoding)
        
        # Calculate statistics for each column
        column_stats = []
        
        for col in df.columns:
            stats = {"name": col, "dtype": str(df[col].dtype)}
            
            # Common stats for all columns
            stats["count"] = df[col].count()
            stats["missing"] = df[col].isna().sum()
            stats["missing_pct"] = (stats["missing"] / len(df)) * 100
            stats["unique"] = df[col].nunique()
            
            # Numeric stats
            if pd.api.types.is_numeric_dtype(df[col]):
                stats["min"] = float(df[col].min()) if not pd.isna(df[col].min()) else None
                stats["max"] = float(df[col].max()) if not pd.isna(df[col].max()) else None
                stats["mean"] = float(df[col].mean()) if not pd.isna(df[col].mean()) else None
                stats["median"] = float(df[col].median()) if not pd.isna(df[col].median()) else None
                stats["std"] = float(df[col].std()) if not pd.isna(df[col].std()) else None
                
            column_stats.append(stats)
            
        return {"file_id": file_id, "columns": column_stats}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating statistics: {str(e)}")

@app.get("/files/{file_id}/visualizations/{column}")
async def get_column_visualization(file_id: str, column: str):
    history = load_upload_history()
    file_info = next((item for item in history if item["file_id"] == file_id), None)
    
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_path = f"uploads/{file_id}.csv"
    encoding_path = f"uploads/{file_id}.encoding"
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="CSV file not found on server")
    
    try:
        # Read the encoding if available
        encoding = 'utf-8'  # Default
        if os.path.exists(encoding_path):
            with open(encoding_path, 'r') as f:
                encoding = f.read().strip()
        
        df = pd.read_csv(file_path, encoding=encoding)
        
        if column not in df.columns:
            raise HTTPException(status_code=400, detail=f"Column '{column}' not found in the CSV file")
        
        visualizations = {}
        
        # Generate visualizations based on data type
        if pd.api.types.is_numeric_dtype(df[column]):
            # Histogram
            fig = px.histogram(df, x=column, title=f"Histogram of {column}")
            visualizations["histogram"] = json.loads(pio.to_json(fig))
            
            # Box plot
            fig = px.box(df, y=column, title=f"Box Plot of {column}")
            visualizations["boxplot"] = json.loads(pio.to_json(fig))
        else:
            # Bar chart for categorical data
            value_counts = df[column].value_counts().reset_index()
            value_counts.columns = [column, 'Count']
            fig = px.bar(value_counts, x=column, y='Count', title=f"Count of {column}")
            visualizations["barplot"] = json.loads(pio.to_json(fig))
        
        return visualizations
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating visualizations: {str(e)}")

@app.get("/files/{file_id}/correlation")
async def get_correlation(file_id: str):
    history = load_upload_history()
    file_info = next((item for item in history if item["file_id"] == file_id), None)
    
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_path = f"uploads/{file_id}.csv"
    encoding_path = f"uploads/{file_id}.encoding"
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="CSV file not found on server")
    
    try:
        # Read the encoding if available
        encoding = 'utf-8'  # Default
        if os.path.exists(encoding_path):
            with open(encoding_path, 'r') as f:
                encoding = f.read().strip()
        
        df = pd.read_csv(file_path, encoding=encoding)
        
        # Get numerical columns
        numerical_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        if len(numerical_cols) < 2:
            return {"message": "Not enough numerical columns for correlation analysis"}
        
        # Calculate correlation matrix
        corr_matrix = df[numerical_cols].corr().round(3)
        
        # Convert to list of dictionaries for JSON response
        corr_data = []
        for i, row in enumerate(corr_matrix.values):
            for j, val in enumerate(row):
                corr_data.append({
                    "x": numerical_cols[j],
                    "y": numerical_cols[i],
                    "correlation": float(val)
                })
        
        # Create heatmap visualization
        fig = px.imshow(
            corr_matrix, 
            x=numerical_cols, 
            y=numerical_cols,
            color_continuous_scale='RdBu_r',
            labels=dict(color="Correlation"),
            text_auto=True
        )
        heatmap_json = json.loads(pio.to_json(fig))
        
        return {
            "correlations": corr_data,
            "visualization": heatmap_json,
            "columns": numerical_cols
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating correlation: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 