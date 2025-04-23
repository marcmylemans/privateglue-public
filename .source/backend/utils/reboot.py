from flask import request

def shutdown_server(shutdown_func):
    if shutdown_func:
        shutdown_func()
    else:
        print("Not running with the Werkzeug server. Manual restart required.")
