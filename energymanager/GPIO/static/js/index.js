loadBtn = document.querySelector("button");

loadBtn.addEventListener("click", async () => {
   let fetchedData = await fetchMeasurementData("api/temps")
   console.log(fetchedData);

});

async function fetchMeasurementData(url) {
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Measurements not available: ${response.status}`);
    }

    const result = await response.json();
    return result;
  } catch (error) {
    console.error(error.message);
  }
}

