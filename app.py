import os
import json
from flask import Flask, request, render_template, jsonify, redirect, url_for
from google.cloud import storage
from google.cloud import pubsub_v1
from google.cloud import bigquery
import plotly.graph_objs as go
import plotly.io as pio
import uuid
from datetime import date

app = Flask(__name__)

# Initialize Google Cloud Storage client
storage_client = storage.Client()
bucket_name = 'health-data-xml-bucket'  # Replace with your bucket name
bucket = storage_client.get_bucket(bucket_name)

# Initialize Pub/Sub client
publisher = pubsub_v1.PublisherClient()
topic_name = 'projects/final-project-444019/topics/health-data-topic'  # Replace with your project ID

# Initialize BigQuery client
client = bigquery.Client()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    if file and file.filename.endswith('.xml'):
        # Save the file to GCS
        blob_name = f"uploads/{str(uuid.uuid4())}.xml"
        blob = bucket.blob(blob_name)
        blob.upload_from_file(file)

        # Trigger the Pub/Sub to process the file
        data = json.dumps({"file": blob_name})
        publisher.publish(topic_name, data.encode('utf-8'))

        # Redirect to metrics page after successful upload
        return redirect(url_for('metrics'))
    
    return jsonify({"error": "Invalid file format!"}), 400

@app.route('/metrics')
def metrics():
    today = date.today()

    # Helper function to query and process data
    def get_data(query):
        results = client.query(query).result()
        data = [{"label": row.label, "value": row.value} for row in results]
        return data

    # WEEKLY DATA (with exact date for each weekday)
    if today.weekday() == 6:  # If today is Sunday (weekday() returns 6 for Sunday), fetch the previous week's data
        weekly_query = """
        SELECT 
          FORMAT_DATE('%Y-%m-%d', DATE(date)) AS label,  -- Full date format (e.g., '2024-12-01')
          SUM(steps) AS value
        FROM 
          `final-project-444019.health_dataset.steps_data`
        WHERE 
          EXTRACT(WEEK FROM date) = EXTRACT(WEEK FROM DATE_SUB(CURRENT_DATE(), INTERVAL 1 WEEK))
          AND EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM DATE_SUB(CURRENT_DATE(), INTERVAL 1 WEEK))
        GROUP BY label
        ORDER BY label  -- Order by label (formatted date) to get sequential days in the week
        """
    else:
        weekly_query = """
        SELECT 
          FORMAT_DATE('%Y-%m-%d', DATE(date)) AS label,  -- Full date format (e.g., '2024-12-01')
          SUM(steps) AS value
        FROM 
          `final-project-444019.health_dataset.steps_data`
        WHERE 
          EXTRACT(WEEK FROM date) = EXTRACT(WEEK FROM CURRENT_DATE())
          AND EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM CURRENT_DATE())
        GROUP BY label
        ORDER BY label  -- Order by label (formatted date) to get sequential days in the week
        """
    weekly_data = get_data(weekly_query)
    weekly_avg = sum(d["value"] for d in weekly_data) / len(weekly_data) if weekly_data else 0
    best_week_day = max(weekly_data, key=lambda x: x["value"]) if weekly_data else None

    # MONTHLY DATA (with daily dates)
    if today.day == 1:  # If today is the 1st day of the month, fetch the previous month's data
        monthly_query = """
        SELECT 
          FORMAT_DATE('%Y-%m-%d', DATE(date)) AS label,  -- Full date format (e.g., '2024-11-01')
          EXTRACT(DAY FROM date) AS day,  -- Extract day of the month for ordering
          SUM(steps) AS value
        FROM 
          `final-project-444019.health_dataset.steps_data`
        WHERE 
          EXTRACT(MONTH FROM date) = EXTRACT(MONTH FROM DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH))
          AND EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH))
        GROUP BY label, day
        ORDER BY label  -- Order by date to get sequential days in the month
        """
    else:
        monthly_query = """
        SELECT 
          FORMAT_DATE('%Y-%m-%d', DATE(date)) AS label,  -- Full date format (e.g., '2024-11-01')
          EXTRACT(DAY FROM date) AS day,  -- Extract day of the month for ordering
          SUM(steps) AS value
        FROM 
          `final-project-444019.health_dataset.steps_data`
        WHERE 
          EXTRACT(MONTH FROM date) = EXTRACT(MONTH FROM CURRENT_DATE())
          AND EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM CURRENT_DATE())
        GROUP BY label, day
        ORDER BY label  -- Order by date to get sequential days in the month
        """
    monthly_data = get_data(monthly_query)
    monthly_avg = sum(d["value"] for d in monthly_data) / len(monthly_data) if monthly_data else 0
    best_month_day = max(monthly_data, key=lambda x: x["value"]) if monthly_data else None

    # YEARLY DATA (with month names)
    if today.timetuple().tm_yday == 1:  # If today is Jan 1, fetch the previous year's data
        yearly_query = """
        SELECT 
          FORMAT_DATE('%b', DATE(date)) AS label,  -- Format to get abbreviated month name (Jan, Feb, Mar)
          EXTRACT(MONTH FROM date) AS month,  -- Extract the numeric month for ordering
          SUM(steps) AS value
        FROM 
          `final-project-444019.health_dataset.steps_data`
        WHERE 
          EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM DATE_SUB(CURRENT_DATE(), INTERVAL 1 YEAR))
        GROUP BY label, month
        ORDER BY month
        """
    else:
        yearly_query = """
        SELECT 
          FORMAT_DATE('%b', DATE(date)) AS label,  -- Format to get abbreviated month name (Jan, Feb, Mar)
          EXTRACT(MONTH FROM date) AS month,  -- Extract the numeric month for ordering
          SUM(steps) AS value
        FROM 
          `final-project-444019.health_dataset.steps_data`
        WHERE 
          EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM CURRENT_DATE())
        GROUP BY label, month
        ORDER BY month
        """
    yearly_data = get_data(yearly_query)
    yearly_avg = sum(d["value"] for d in yearly_data) / len(yearly_data) if yearly_data else 0
    best_year_month = max(yearly_data, key=lambda x: x["value"]) if yearly_data else None

    # Generate Charts
    def generate_chart(data, avg, title, x_title, y_title):
      bars = go.Bar(
          x=[d["label"] for d in data],
          y=[d["value"] for d in data],
          name="Steps",
          marker=dict(
              color="orangered",  # Orange bars like Apple Health
          ),
      )
      avg_line = go.Scatter(
          x=[d["label"] for d in data],
          y=[avg] * len(data),
          mode="lines",
          name="Average",
          line=dict(color="gray", width=2),  # Solid gray line
      )

      # # Find the max value of the bars to place the annotation safely above them
      # y_max = max(d["value"] for d in data)

      # Check if data is empty
      if data:
          # Find the max value of the bars to place the annotation safely above them
          y_max = max(d["value"] for d in data)

          # Adding padding for annotation placement to ensure it is above the max bar
          padding = 0.1 * y_max  # 10% padding above the maximum value of the bars

          annotation_y = y_max + padding  # Place the annotation above the bars, with padding
      else:
          # If data is empty, set a default value for y_max or skip annotation
          y_max = 0
          annotation_y = 0  # Skip or set a default safe position for annotation

      # Adding padding for annotation placement to ensure it is above the max bar
      padding = 0.1 * y_max  # 10% padding above the maximum value of the bars
      
      annotation_y = y_max + padding  # Place the annotation above the bars, with padding

      annotations = [
          dict(
              x=data[len(data) // 2]["label"],  # Position the annotation at the center of the x-axis
              y=annotation_y,
              text=f"Average: {round(avg, 2)}",  # Display average value
              showarrow=False,
              font=dict(color="white", size=14),  # White color for the annotation text
              align="center",
          )
      ]

      layout = go.Layout(
          title=title,
          xaxis=dict(title=x_title, showgrid=False),
          yaxis=dict(title=y_title, showgrid=False),
          barmode="group",
          annotations=annotations,
          plot_bgcolor='rgb(27, 27, 27)',  # Dark grey background
          paper_bgcolor='rgb(27, 27, 27)',  # Dark grey paper background
      )
      
      return pio.to_json(go.Figure(data=[bars, avg_line], layout=layout))




    weekly_chart = generate_chart(weekly_data, weekly_avg, "Current Week Steps Trend", "Date", "Steps")
    monthly_chart = generate_chart(monthly_data, monthly_avg, "Current Month Steps Trend", "Day", "Steps")
    yearly_chart = generate_chart(yearly_data, yearly_avg, "Current Year Steps Trend", "Month", "Steps")

    return render_template(
        "metrics.html",
        weekly_chart=weekly_chart,
        monthly_chart=monthly_chart,
        yearly_chart=yearly_chart,
        best_week_day=best_week_day,
        best_month_day=best_month_day,
        best_year_month=best_year_month,
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
