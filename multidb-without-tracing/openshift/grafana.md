Grafana Dashboard Instructions for Multi-Database Monitoring
This guide provides instructions on how to create Grafana panels to visualize latency and write failures for multiple databases, leveraging the database_name label exposed by your application's Prometheus metrics.

Prerequisites
Before you begin, ensure you have:

Your Flask Application Running: The application must be exposing Prometheus metrics (e.g., at /metrics) with the database_name label on db_write_latency_seconds, db_write_success_total, db_write_failure_total, and db_write_timeout_total.

Prometheus Setup: Prometheus is configured to scrape your application's /metrics endpoint.

Grafana Setup: Grafana is running and has a Prometheus data source configured that points to your Prometheus instance.

Panel 1: Visualize Write Failures Across All Databases
This panel will show the rate of database write failures, broken down by each database, or as a combined total.

Option A: Failure Rate Per Database (Graph Panel)
This is ideal for seeing how each database's failure rate trends over time.

Add a new panel to your Grafana dashboard.

Choose the Graph visualization.

In the Query tab:

Select your Prometheus data source.

Enter the PromQL query:

rate(db_write_failure_total[5m])


Explanation:

db_write_failure_total: Your counter metric for failed writes.

[5m]: Specifies a 5-minute range vector, used with rate(). Adjust this duration as needed for your desired granularity.

rate(): Calculates the per-second average rate of increase for the counter over the last 5 minutes. Prometheus will automatically return a separate time series for each unique database_name label.

In the Viz (Visualization) tab:

Legend: In the "Legend" section, use {{database_name}} to dynamically show the name of each database in the legend (e.g., "production_db", "analytics_db").

Option B: Total Failure Rate (Graph or Stat Panel)
This provides an aggregate view of failures across all databases.

Add a new panel.

Choose Graph or Stat visualization.

In the Query tab:

Enter the PromQL query:

sum(rate(db_write_failure_total[5m]))


Explanation:

sum(): Aggregates the rate of db_write_failure_total across all database_name labels, resulting in a single time series.

In the Viz tab:

For a Graph panel, the legend will simply be the metric name unless you manually override it.

For a Stat panel, the main value will show the current aggregated rate.

Panel 2: Visualize Write Latency Across All Databases (P90)
Latency is best viewed using percentiles from the histogram metric. The 90th percentile (P90) is a good starting point, showing the latency below which 90% of your requests complete.

Add a new panel to your Grafana dashboard.

Choose the Graph visualization.

In the Query tab:

Select your Prometheus data source.

Enter the PromQL query:

histogram_quantile(0.90, sum(rate(db_write_latency_seconds_bucket[5m])) by (le, database_name))


Explanation:

db_write_latency_seconds_bucket: The cumulative counter metric for histogram buckets.

[5m]: A 5-minute range vector.

rate(): Calculates the per-second rate of observations for each histogram bucket.

sum(...) by (le, database_name): Aggregates the rates of all _bucket series. It's crucial to sum by le (the upper bound of the bucket) and database_name to correctly calculate quantiles per database.

histogram_quantile(0.90, ...): Computes the 90th percentile from the aggregated histogram data.

In the Viz tab:

Legend: Use {{database_name}} to show a distinct line for each database's P90 latency.

Units: Set the unit to Time -> seconds (or milliseconds if your latencies are consistently low) for clear readability.

Y-axis: Adjust the min/max values to fit your expected latency range for better visualization.

Panel 3: Combined Metrics (Table Panel)
A table panel can provide a quick, consolidated overview of various key metrics (e.g., current success count, current failure count, current P90 latency) for each database in one glance.

Add a new panel to your Grafana dashboard.

Choose the Table visualization.

In the Query tab, add multiple queries, one for each metric you want to display:

Query A (Success Count):

sum by (database_name) (db_write_success_total)


Note: Using sum by (database_name) ensures you get one result per database, showing the total accumulated successful writes.

Query B (Failure Count):

sum by (database_name) (db_write_failure_total)


Note: Similar to success count, shows accumulated failures per database.

Query C (P90 Latency - Current):

histogram_quantile(0.90, sum by (le, database_name) (db_write_latency_seconds_bucket))


Note: This query returns the current 90th percentile latency for each database.

Go to the Transform tab (next to the Query tab):

Transformation 1: Reduce (Optional, for latest values)

Click "Add transformation" -> "Reduce".

Set "Calculation" to Last (or Last * (not null)). This ensures you're only showing the most recent value for each metric.

Transformation 2: Join by field (Crucial for combining rows)

Click "Add transformation" -> "Join by field".

Select database_name as the "Field". This will merge the rows from Query A, B, and C that share the same database_name label.

Transformation 3: Organize fields by name (For clean column headers)

Click "Add transformation" -> "Organize fields by name".

Here, you can rename your columns (e.g., Value #A to Success Count, Value #B to Failure Count, Value #C to P90 Latency). You can also hide the Time fields if they're not relevant for your table view.

In the Viz tab (Table specific settings):

Adjust column widths and apply value formatting (e.g., seconds for latency, decimal(0) for counts).

General Grafana Dashboard Tips
Dashboard Variables: Consider creating a dashboard variable (e.g., named database) that is populated by label_values(db_write_success_total, database_name). You can then use this variable in your PromQL queries (e.g., rate(db_write_failure_total{database_name="$database"}[5m])) to allow users to filter the dashboard by a specific database.

Time Range: Ensure your dashboard's time range is appropriate for the data you want to view (e.g., "Last 6 hours", "Last 24 hours").

Alerting: Once your panels are set up, you can configure Grafana alerts directly from these panels to notify you of high latency or increased failure rates for any of your databases.

Row Organization: Group related panels into rows (e.g., "Database Health Overview", "Detailed Latency Trends").

By following these instructions, you'll have a powerful and flexible Grafana dashboard to monitor the health and performance of all your interconnected databases.