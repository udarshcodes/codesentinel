import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/backend")
from api.job_manager import JobManager
from database import get_connection

task_id = "test-task-123456"
JobManager.create_job(task_id, "https://github.com/udarshcodes/portfolio")

conn = get_connection()
row = conn.cursor().execute("SELECT pipeline_state FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
print("After create_job:", row)

worker_id = JobManager.claim_waiting_job(task_id)
row2 = conn.cursor().execute("SELECT pipeline_state FROM jobs WHERE task_id = ?", (task_id,)).fetchone()
print("After claim_waiting_job:", row2)

job = JobManager.get_job(task_id)
print("From get_job:", job.get('pipeline_state'))

conn.close()
