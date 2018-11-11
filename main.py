import ConfigParser
import logging
import colony_manager
import booking_manager
import user_manager
import bcrypt

from flask import Flask, flash, render_template, session, url_for, request, redirect
from flask_mail import Mail, Message
from functools import wraps
from database import get_db, init_db
from logging.handlers import RotatingFileHandler
from flask import Flask, url_for

app = Flask(__name__)
app.secret_key = 'super duper secret key'

mail_settings = {
	"MAIL_SERVER": 'smtp.gmail.com',
  	"MAIL_PORT": 465,
	"MAIL_USE_TLS": False,
 	"MAIL_USE_SSL": True,
	"MAIL_USERNAME": 'solarstart.bookings@gmail.com',
 	"MAIL_PASSWORD": 'Test123!'
}

app.config.update(mail_settings)
mail = Mail(app)

@app.route('/')
def home():
  return render_template('home_page.html')


@app.route('/test/')
def test(): 
  app.logger.info("info")
  app.logger.debug("debug")
  app.logger.warn("warn")
  app.logger.error("error")
  return render_template('test.html')

@app.route('/logout/')
def logout():
  session['logged_in'] = False
  session['admin'] = False  
  session.pop('user', None) 
  return redirect(request.referrer)
  
@app.route('/login/', methods=['POST'])
def login():
  try:
    if user_manager.login_user(request.form):
      session['logged_in'] = True
      email = request.form['user_email']    
      session['user'] = user_manager.get_user(email).__dict__
          
      app.logger.info("User successfully logged in with email: ", email)
    if email == 'admin':
      app.logger.info("User: '" + session['user']['username'] + "' has Admin permissions")
      session['admin'] = True
  except:
    return render_template('login_error.html')  
  return redirect(request.referrer)
   
  
@app.route('/register/', methods=['POST'])
def register_user():
  user_manager.add_new_user(request.form)
  return redirect(request.referrer)

def requires_login(f):
  @wraps(f)
  def decorated(*args, **kwargs):
    status= session.get('logged_in', False)
    if not status: 
      return redirect(url_for('.home'))
    return f(*args, **kwargs)
  return decorated
  
def requires_admin(f):
  @wraps(f)
  def decorated(*args, **kwargs):
    status = session.get('admin', False)
    if not status:
      return redirect(url_for('.home'))
    return f(*args, **kwargs)
  return decorated

@app.route('/db/')
@requires_login
def db():

  db = get_db()
  
  page = []
  page.append('<html><ul>')
  sql = "SELECT rowid, * FROM booking_ads ORDER BY booking_ad_id" 
  for row in db.cursor().execute(sql):
    page.append('<li >') 
    page.append(str(row))
    page.append('</li >')
  page.append('</ul><html>')
  return ''.join(page)

@app.route('/admin_editor/')
@requires_admin
def admin_editor():
  return render_template('admin_editor.html')

@app.route('/admin_editor/add_colony_ad', methods=['GET', 'POST'])
@requires_admin
def add_colony_ad():
  if request.method == 'POST':
    image = request.files['image']  
    colony_manager.add_colony_ad(request.form, image)

  return render_template('add_colony_ad.html')

@app.route('/admin_editor/remove_colony_ad', methods=['GET', 'POST'])
@requires_admin
def remove_colony_ad():
  if request.method == 'POST':
    colony_ad_id = request.form['colony_ad_id']
    colony_manager.remove_colony_ad(colony_ad_id)
  
  return render_template('remove_colony_ad.html')

@app.route('/colony_ads/<string:location>/')
def colony_ads_index(location):
  colony_ads = colony_manager.get_colony_ads(location)
  
  if colony_ads:   
    return render_template('colony_ad_index.html', colony_ads = colony_ads)
  return redirect(url_for('.home'))

@app.route('/colony_ads/<string:location>/colony_id/<int:colony_id>')
def view_colony_ad(location, colony_id):
  colony = colony_manager.get_colony(colony_id)
  return render_template('view_colony_ad.html', colony=colony)

@app.route('/booking/colony_id/<int:colony_id>', methods=['GET', 'POST'])
def book_colony(colony_id):
  if request.method == 'POST':
    try:
      if session['logged_in']:
        user_id = session['user']['user_id']
        app.logger.info("Create booking for user and write to db")
        booking_manager.create_booking(request.form, user_id, colony_id) 
        
        app.logger.info("Send booking confirmation email")
        send_confirmation_email(request.form)
        return render_template('booking_confirmation.html', email=session['user']['user_email'])  
      else:
        app.logger.info("User not logged in, flashing error message")
        flash("Please log in to complete your booking")
    except KeyError:
      app.logger.info("KeyError encountered for 'logged_in' session, flashing error message")
      flash("Please log in to complete your booking")

  colony = colony_manager.get_colony(colony_id) 
     
  return render_template('book_colony.html', colony=colony)

def send_confirmation_email(request):
      email = session['user']['user_email'] 
      username = session['user']['username']
      
      total_cost = int(request['cost']) * int(request['number_of_people'])  
      colony_name = request['colony_name']
      number_of_people = request['number_of_people']  
 
      with app.app_context():
        msg = Message(subject="SolarStart Booking Confirmation",
                      sender=app.config.get("MAIL_USERNAME"), 
                      recipients=[email])
        msg.html = render_template('email_confirmation.html', username=username, spaces=number_of_people, total_cost=total_cost, colony_name=colony_name)
        mail.send(msg) 

@app.route('/<string:username>/mybookings')
@requires_login
def view_bookings(username):
  user_id = session['user']['user_id']
  app.logger.info("User: " + str(user_id) + " requests to view their bookings, getting user's bookings") 

  bookings = booking_manager.get_bookings_for_user(user_id)
  
  colonies = []

  app.logger.info("Get colony ads associated with user bookings")
  for booking in bookings:
    colonies.append(colony_manager.get_colony(booking.colony_id))

  app.logger.info("Remove duplicate colony ads")
  colonies = colony_manager.remove_duplicates(colonies)
 
  return render_template('view_bookings.html', bookings=bookings, colonies=colonies)

@app.route('/results/', methods=['GET', 'POST'])
def search():
  colony_ads = []
  if request.method == 'POST':
    term = request.form['search_term']
    colony_ads = colony_manager.search_colony_ads(term)
     
  return render_template('colony_ad_index.html', colony_ads = colony_ads)

@app.errorhandler(404)
def page_not_found(error):
  return render_template('404_error.html'), 404

def init(app):
  config = ConfigParser.ConfigParser() 
  try:
    config_location = "etc/logging.cfg" 
    config.read(config_location)
    
    app.config['DEBUG'] = config.get("config", "debug") 
    app.config['ip_address'] = config.get("config", "ip_address") 

    app.config['port'] = config.get("config", "port") 
    app.config['url'] = config.get("config", "url") 

    app.config['log_file'] = config.get("logging", "name") 
    app.config['log_location'] = config.get("logging", "location")
    app.config['log_level'] = config.get("logging", "level") 

  except:   
    print "Error reading logging configuration file at: ", config_location

def logs(app):
  log_pathname = app.config['log_location'] + app.config['log_file']
  file_handler = RotatingFileHandler(log_pathname, maxBytes=1024* 1024 * 10, backupCount=1024) 
  file_handler.setLevel(app.config['log_level'])  
  formatter = logging.Formatter("%(levelname)s | %(asctime)s | %(module)s | %(funcName)s | %(message)s") 
  file_handler.setFormatter(formatter) 
  
  app.logger.setLevel( app.config['log_level'] ) 
  app.logger.addHandler(file_handler)


if __name__ == "__main__":
  init(app)
  logs(app)

  app.run(
      host=app.config['ip_address'],
      post=int(app.config['port']))



