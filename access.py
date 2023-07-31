from app import app

@app.template_filter('nl2br')
def nl2br(item):
    if isinstance(item, str):
        return item.replace('\n','<br>')
    return item

@app.template_filter('isadmin')
def isadmin(item):
    if isinstance(item, tuple):
        return 1 in item
    return False

@app.template_filter('isusrmgr')
def isusrmgr(item):
    if isinstance(item, tuple):
        return 2 in item
    return False

@app.template_filter('isfawa')
def isfawa(item):
    if isinstance(item, tuple):
        return 3 in item
    return False

@app.template_filter('issms')
def issms(item):
    if isinstance(item, tuple):
        return 4 in item
    return False

@app.template_filter('ispayroll')
def ispayroll(item):
    if isinstance(item, tuple):
        return 5 in item
    return False

@app.template_filter('isreadonly')
def isreadonly(item):
    if isinstance(item, tuple):
        return 6 in item
    return False

@app.template_filter('nl2br')
def nl2br(item):
    if isinstance(item, str):
        return item.replace('\n','<br>')
    return item

@app.template_filter('hasauth')
def hasauth(item, check):
    # "item" and "check" are lists. The correct authorization categories are in "check"
    # if an item in "item" corresponds to an item in "check" then return True
    # example item=(3,4) and check=(2,4) --> return True
    # example item=(2,4,5) and check=(3,6) --> return False
    # example item=(1,) and check=(2,3) --> return True (because 1=admin)
    if 1 in item:
        return True
    auth = False
    for element in item:
        if element in check:
            auth = True
    return auth
