module.exports = {
  apps: [
    {
      name: "ai-employee-cloud",
      script: "/home/ubuntu/ai-employee/cloud/start_cloud.sh",
      cwd: "/home/ubuntu/ai-employee",
      max_restarts: 10,
      min_uptime: "30s",
      restart_delay: 5000,
      log_file: "/home/ubuntu/ai-employee/logs/cloud-agent.log",
      error_file: "/home/ubuntu/ai-employee/logs/cloud-agent-error.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      watch: false,
    },
    {
      name: "health-monitor",
      script: "/home/ubuntu/ai-employee/cloud/start_health.sh",
      cwd: "/home/ubuntu/ai-employee",
      max_restarts: 5,
      log_file: "/home/ubuntu/ai-employee/logs/health.log",
      error_file: "/home/ubuntu/ai-employee/logs/health-error.log",
      watch: false,
    },
  ],
};
