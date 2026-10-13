import uuid
def brand(request):
    return {'request_id':str(uuid.uuid4()),'brand_name':"Rocky’s Worldwide Chauffeured Transportation"}
