document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('createVpsForm');
    if (!form) return;

    form.addEventListener('submit', function(e) {
        const modal = document.getElementById('vpsLoaderModal');
        const stepText = document.getElementById('loaderStepText');
        const progressBar = document.getElementById('progressBar');

        modal.style.display = 'flex';

        const steps = [
            { text: "Allocating container & filesystem...", progress: 25, delay: 1000 },
            { text: "Setting up IP networking & port forwarding...", progress: 50, delay: 3000 },
            { text: "Configuring root password & SSH security...", progress: 75, delay: 5500 },
            { text: "Finalizing startup sequence...", progress: 95, delay: 7500 }
        ];

        steps.forEach(step => {
            setTimeout(() => {
                stepText.innerText = step.text;
                progressBar.style.width = step.progress + "%";
            }, step.delay);
        });
    });
});
