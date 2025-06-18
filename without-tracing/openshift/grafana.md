Grafana Configuration Guide (Updated for Histogram Latency)
Grafana allows you to query, visualize, alert on, and understand your metrics. This guide is updated to specifically show how to visualize the Histogram metric for database write latency, providing insights into the distribution of individual request times.

Step 1: Access Your Grafana Instance
First, you need to access your Grafana instance.

OpenShift Monitoring Stack: If you're using OpenShift's built-in monitoring, you can usually find Grafana via the OpenShift console under "Developer Console" -> "Monitoring" -> "Dashboards" or through a dedicated route (e.g., grafana.<your-cluster-domain>).

Standalone Grafana: If you've deployed Grafana separately, navigate to its URL (e.g., http://localhost:3000 if running locally).

You'll need administrative access to add data sources and create dashboards.

Step 2: Add Prometheus as a Data Source
Grafana needs to know where to get the data from.

Navigate to Data Sources:

From the Grafana home dashboard, click on the Gear icon (Configuration) in the left-hand navigation pane.

Select "Data sources".

Add New Data Source:

Click the "Add data source" button.

Search for and select "Prometheus".

Configure Prometheus Data Source:

Name: Give it a descriptive name, e.g., OpenShift Prometheus or My Flask App Prometheus.

URL: This is the most crucial part. It's the URL of your Prometheus server that's scraping your Flask app.

For OpenShift's Built-in Prometheus: This is often an internal ClusterIP service. A common URL format is http://prometheus-k8s.openshift-monitoring.svc.cluster.local:9090 (adjust if your cluster's monitoring stack uses a different service name or port). You can often find this by inspecting the Prometheus pod's service within OpenShift.

For External Prometheus: Use the URL where your Prometheus instance is accessible (e.g., http://localhost:9090 if running Prometheus locally).

Access: Set to Server (default) unless you have specific proxy requirements.

Authentication: If your Prometheus requires authentication, configure it here (e.g., basic auth, TLS client auth). OpenShift's internal Prometheus usually doesn't require extra config if Grafana is also in OpenShift.

Save & Test: Click the "Save & Test" button. You should see a "Data source is working" message. If not, double-check the Prometheus URL and any authentication settings.

Step 3: Create a New Dashboard
Once your Prometheus data source is configured, you can start building dashboards.

Navigate to Dashboards:

From the Grafana home dashboard, click on the "Plus icon (+)" in the left-hand navigation pane.

Select "New dashboard".

Add an Empty Panel:

Click on "Add new panel" or "Add an empty panel".

Step 4: Add Panels and Visualize Metrics
Now, let's add panels for each of the Prometheus metrics exposed by your Flask app.

For each new panel:

Select Data Source: In the "Query" tab, ensure your newly configured Prometheus data source is selected.

Enter PromQL Query: Type the Prometheus Query Language (PromQL) query.

Choose Visualization: Select the appropriate visualization type (e.g., Graph, Stat, Gauge).

Configure Panel Options: Adjust title, units, legend, axes, etc.

Panel 1: Database Write Latency (90th and 99th Percentiles)
Metric: db_write_latency_seconds (Histogram metric)

What it shows: This visualizes specific percentiles of your database write latencies over time. For example, the 90th percentile (p90) means 90% of your requests completed within that time, giving you a better idea of user experience than just the average.

PromQL Query (90th Percentile):

histogram_quantile(0.90, rate(db_write_latency_seconds_bucket[5m]))

PromQL Query (99th Percentile):

histogram_quantile(0.99, rate(db_write_latency_seconds_bucket[5m]))

db_write_latency_seconds_bucket: This is the raw metric exposed by the Histogram, showing cumulative counts for each latency bucket.

rate(...[5m]): Calculates the per-second rate of increase for each bucket over the last 5 minutes.

histogram_quantile(0.90, ...): This function calculates the 90th percentile from the histogram buckets.

Visualization Type: Graph

Panel Title: DB Write Latency Percentiles (p90, p99)

Units: seconds (under Standard options -> Unit)

Description: Use this to identify outliers or "long tail" latencies. High percentiles indicate that a significant portion of your users (or writes) are experiencing slower responses. Add both queries to the same panel to compare.

Panel 2: Database Write Latency (Heatmap / Bucket Distribution)
Metric: db_write_latency_seconds_bucket (Histogram metric)

What it shows: This provides a visual representation of how many requests fall into each latency bucket over time. It's excellent for spotting shifts in latency distribution (e.g., if suddenly more requests are falling into higher latency buckets).

PromQL Query:

sum by (le) (rate(db_write_latency_seconds_bucket[5m]))

sum by (le): Aggregates the rates by the le (less than or equal to) label, which represents the upper bound of each bucket.

rate(db_write_latency_seconds_bucket[5m]): Calculates the rate of observations per bucket over the last 5 minutes.

Visualization Type: Heatmap

Panel Title: DB Write Latency Heatmap

X-axis: Time

Y-axis: le (latency buckets) - Grafana will automatically configure this for Heatmap.

Data Options: Ensure "Format" is set to "Heatmap" if available in your Grafana version.

Description: The darker areas indicate more requests in that latency range. A shift towards higher le values (upper part of the heatmap) means latencies are increasing.

Panel 3: Total Successful Database Writes
Metric: db_write_success_total (Counter metric)

What it shows: The cumulative count of successful database write operations since the application started.

PromQL Query:

db_write_success_total

Visualization Type: Stat (to show the current total) or Graph (to show the rate over time)

If Stat:

Panel Title: Total Successful DB Writes

Display: Show "Current" value.

If Graph (to see writes per second):

PromQL Query: rate(db_write_success_total[1m])

Panel Title: Successful DB Writes Per Second

Units: operations/sec

Description: A steadily increasing counter is good. If the rate drops unexpectedly, it could indicate a problem.

Panel 4: Total Failed Database Writes
Metric: db_write_failure_total (Counter metric)

What it shows: The cumulative count of failed database write operations.

PromQL Query:

db_write_failure_total

Visualization Type: Stat or Graph (to see the rate of failures)

If Stat:

Panel Title: Total Failed DB Writes

If Graph (to see failures per second):

PromQL Query: rate(db_write_failure_total[1m])

Panel Title: Failed DB Writes Per Second

Units: operations/sec

Description: This counter should ideally be zero or very low. Any significant increase indicates issues with database connectivity, permissions, or integrity.

Panel 5: Total Database Write Timeouts (Simulated)
Metric: db_write_timeout_total (Counter metric)

What it shows: The cumulative count of database write operations that resulted in a timeout (simulated in your app).

PromQL Query:

db_write_timeout_total

Visualization Type: Stat or Graph (to see the rate of timeouts)

If Stat:

Panel Title: Total DB Write Timeouts

If Graph (to see timeouts per second):

PromQL Query: rate(db_write_timeout_total[1m])

Panel Title: DB Write Timeouts Per Second

Units: operations/sec

Description: Similar to failures, this should be low. High timeout counts suggest network issues, database overload, or configuration problems.

Step 5: Save Your Dashboard
Once you've added all your desired panels and configured them:

Click the "Save dashboard" icon (usually a floppy disk icon or similar) at the top of the dashboard page.

Give your dashboard a Name (e.g., Flask DB Monitoring).

You can optionally add it to a folder or add tags for organization.

Click "Save".

Further Enhancements for your Grafana Dashboard:
Dashboard Variables: Use Grafana variables (e.g., for instance, job, or pod) to allow users to filter metrics by specific application instances or environments. This is especially useful if you scale your Flask app to multiple pods.

Alerting: Configure alerts in Grafana based on these metrics. For example, trigger an alert if rate(db_write_failure_total[1m]) is consistently above zero, or if a high latency percentile exceeds a certain threshold.

Row Organization: Group related panels into rows for better readability.

Time Range: Adjust the dashboard's time range to view historical data or focus on real-time activity.

Annotations: Add annotations to mark deployment events or known incidents, making it easier to correlate changes with metric behavior.

By following these steps, you'll have a robust Grafana dashboard providing real-time insights into your Flask application's database write performance and reliability on OpenShift, with a detailed view of latency distribution.