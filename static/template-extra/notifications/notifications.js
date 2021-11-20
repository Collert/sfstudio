function dismissNotification(notificationId){
    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/notifications");
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded'); //One day I'll find out what this is
    xhr.send("id=" + notificationId);
    hideNotification(notificationId);
}
function hideNotification(notificationId){
    $("#notification" + notificationId).slideUp()
    var notification = document.getElementById(`notification${notificationId}`);
    notification.hide()
}