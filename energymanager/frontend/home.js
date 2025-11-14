async function fetchDataFromApi(endpoint) {
   try {
      const response = await fetch(endpoint);

      if (!response.ok) {
         throw new Error(`Response status: ${response.status}`);
      }

      const values = await response.json();
      return values;
   
   } catch (error) {
      console.error(error);
   }
   
}