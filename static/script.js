// Call your Python backend
async function callGeminiAI(prompt) {
    try {
        const response = await fetch("http://localhost:5000/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt: prompt })
        });

        const data = await response.json();
        return data.result;
    } catch (error) {
        console.error("Error calling AI:", error);
        return "Error fetching AI response.";
    }
}

// Example: trigger on button click
document.getElementById("analyzeBtn").addEventListener("click", async () => {
    const disasterInfo = "Flood in coastal region, 10,000 displaced";
    const result = await callGeminiAI(`Analyze this disaster situation: ${disasterInfo}`);
    document.getElementById("aiOutput").innerText = result;
});

// Example: disaster summary with structured data
async function getDisasterSummary(disasterData) {
    const response = await fetch("http://localhost:5000/api/disaster-summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ disaster_data: disasterData })
    });
    const data = await response.json();
    return data.summary;
}