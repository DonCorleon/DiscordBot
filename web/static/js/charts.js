/**
 * Chart.js configurations and updates
 */

let commandsChart = null;

// Initialize charts when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    initCommandsChart();
});

function initCommandsChart() {
    const ctx = document.getElementById('commands-chart');
    if (!ctx) return;

    commandsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Command Usage',
                data: [],
                backgroundColor: 'rgba(88, 101, 242, 0.8)',
                borderColor: 'rgba(88, 101, 242, 1)',
                borderWidth: 2,
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(45, 45, 45, 0.95)',
                    titleColor: '#fff',
                    bodyColor: '#e0e0e0',
                    borderColor: '#5865F2',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: false,
                    callbacks: {
                        label: function(context) {
                            return `${context.parsed.y} uses`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: '#b0b0b0',
                        precision: 0
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                },
                x: {
                    ticks: {
                        color: '#b0b0b0'
                    },
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

function updateCommandsChart(commandsData) {
    if (!commandsChart) return;

    // commandsData has a 'stats' array
    const commands = commandsData?.stats;

    if (!commands || commands.length === 0) {
        console.log('No command stats available');
        return;
    }

    console.log('Command stats:', commands);

    // Sort by total uses and take top 10
    const topCommands = commands
        .sort((a, b) => b.total_uses - a.total_uses)
        .slice(0, 10);

    const labels = topCommands.map(cmd => `~${cmd.command_name}`);
    const data = topCommands.map(cmd => cmd.total_uses);

    // Update chart
    commandsChart.data.labels = labels;
    commandsChart.data.datasets[0].data = data;
    commandsChart.update('none'); // 'none' for no animation on update
}

// Export for use in dashboard.js
window.updateCommandsChart = updateCommandsChart;

console.log('📈 Charts initialized');
