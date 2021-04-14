var name = document.querySelector("#name").innerText;
var new_name = [];
for(letter in name){
    if(letter === 0){
        new_name[letter] = "<span class='flicker-2'>" + name[letter] + "</span>"
    }
    else if(letter%5 === 0){
        new_name[letter] = "<span class='flicker-2'>" + name[letter] + "</span>"
    }
    else{
        new_name[letter] = name[letter]
    }
}
new_name = new_name.join('');
setTimeout(function(){ document.querySelector("#name").innerHTML = new_name; }, 5000);