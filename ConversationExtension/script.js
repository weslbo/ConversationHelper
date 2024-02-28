function retrieveAudio() {
    console.log("Retrieving audio")
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
        const currentTab = tabs[0];

        fetch("http://localhost:7071/api/retrieve_conversation?url=" + currentTab.url)
          .then(response => response.blob())
          .then(blob => {
            document.getElementById("title").innerText = "Ready to listen?";
            document.getElementById("audio").src = URL.createObjectURL(blob);
          })
          .catch(err =>  {
            document.body.style.backgroundColor = "red";
            document.getElementById("title").innerText = err;
          });
       
        document.body.style.backgroundColor = "lightblue";
        
        // You can do more with the currentTab variable
        console.log(currentTab);
      });
}

retrieveAudio()