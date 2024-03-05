from flask import Flask, request
from flask_restx import Api, Resource, fields
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import asc, desc, func
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy.sql.expression import cast
import datetime
import os
import matplotlib.pyplot as plt
import io
import sys
from flask import send_file

# Get the path of the directory where the Python file is located
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)

# Get current dir
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'Calendar.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

api = Api(app, version='1.0', title='MyCalendar API', description='A time-management and scheduling calendar service (Google Calendar) for Australians using Flask-Restx.')

ns = api.namespace('events', description='Events operations')

# examples:
event = api.model('calendar', {
    'id': fields.Integer(readonly=True, description='The event unique identifier'),
    'name': fields.String(required=True, description='The event name', example='Event name'),
    'date': fields.Date(required=True, description='The event date', dt_format='%d-%m-%Y', example='03-04-2021'),
    'from': fields.String(required=True, description='The start time of the event', dt_format='%H:%M:%S', example='15:00:00'),
    'to': fields.String(required=True, description='The end time of the event', dt_format='%H:%M:%S', example='17:00:00'),
    'location': fields.Nested(api.model('Location', {
        'street': fields.String(required=True, description='The street address of the location', example='Abc St'),
        'suburb': fields.String(required=True, description='The suburb of the location', example='Sydney'),
        'state': fields.String(required=True, description='The state of the location', example='NSW'),
        'post_code': fields.Integer(required=True, description='The post code of the location', example='2000')})),
    'description': fields.String(required=True, description='The description of the event', example='Description'),
    'last-update': fields.String(readonly=True, description='the time the collection is stored in the database'),
})

postResponse = api.model('post-response', { ## Example response
    'id': fields.Integer(readonly=True, description='The event unique identifier'),
    'last-update': fields.Integer(example = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    '_links': fields.Nested(api.model('links',{
        "self": fields.Nested(api.model('self',{
            'heref': fields.String(example = '/events/0'),}))
    })),
}, doc=False)

statsResponse = api.model('stats-response', {
    "total": fields.Integer(example = 10),
    "total-current-week": fields.Integer(example = 5),
    "total-current-month": fields.Integer(example = 8),
    "per-days": fields.Nested(api.model('per-days', {
    })),
})

########################## db model ##########################
class Model(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    startTime = db.Column(db.String(10), nullable=False)
    endTime = db.Column(db.String(10), nullable=False)
    street = db.Column(db.String(20), nullable=False)
    suburb = db.Column(db.String(10), nullable=False)
    state = db.Column(db.String(3), nullable=False)
    post_code = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(100), nullable=False)
    last_update = db.Column(db.String(20), nullable=False)

    def __repr__(self):
        return f'Event {self.id}'

class eventDAO(object):
    ######################## 1.GET ###########################
    def get(self, id):
        event = Model.query.filter_by(id=id).first()

        if event:
            response = {'id': event.id, 'last-update':event.last_update, 'name': event.name, 'date': event.date, 
            'from': event.startTime, 'to': event.endTime, 
            'location':{
                'street': event.street,
                'suburb': event.suburb,
                'state': event.state,
                'post_code': event.post_code,
            },
            'descrtiption': event.description,
            '_links': {}}
            response['_links']['self'] = {"href": f"/events/{event.id}"}
            previous_event = Model.query.order_by(Model.date.desc(), Model.startTime.desc()).filter(Model.date <= event.date,
                    Model.startTime < event.startTime).first()
            next_event = Model.query.order_by(Model.date.asc(), Model.startTime.asc()).filter(Model.date >= event.date,
                    Model.startTime > event.startTime).first()
            if previous_event:
                response['_links']['previous'] = {"href": f"/events/{previous_event.id}"}
            if next_event:
                response['_links']['next'] = {"href": f"/events/{next_event.id}"}
            return response
        else:
            api.abort(404, f"Event {id} doesn't exist")



    ############################ 2. POST ##########################
    @api.expect(event)
    def create(self, data):
        # Check if there are any events that overlap with the new event
        existing_events = Model.query.filter_by(date=data['date']).all() # have to be at the same day
        for event in existing_events:
            if event.startTime <= data['from'] < event.endTime:
                api.abort(400, 'Event overlaps with existing event')
            elif event.startTime < data['to'] <= event.endTime:
                api.abort(400, 'Event overlaps with existing event')

        
        required_fields = ['name', 'date', 'from', 'to', 'location', 'description']
        if not all(key in data for key in required_fields):
            api.abort(400, 'All fields are required')

        # Create event model
        event = Model(name=data['name'], date=data['date'], startTime=data["from"], endTime=data["to"], 
                      street=data['location']['street'], suburb=data['location']['suburb'], state=data['location']['state'], 
                      post_code=data['location']['post_code'], description=data['description'], 
                      last_update=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        db.session.add(event)
        db.session.commit()
        # Response body
        return {'id': event.id, 'last-update':datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                '_links': {"self": {'href': f'/events/{event.id}'}
        }}

    ###########################3. DELETE ###########################
    def delete(self, id):
        event = Model.query.filter_by(id=id).first()
        if not event:
            api.abort(404, f"Event with id {id} doesn't exist")
        db.session.delete(event)
        db.session.commit()

    ############################ 4. PATCH #############################
    def update(self, id, data):
        event = Model.query.filter_by(id=id).first()
        if not event:
            api.abort(404, f"Event with id {id} doesn't exist")
        for attribute in data:
            if attribute in ['name', 'date', 'description']:
                setattr(event, attribute, data[attribute])
            elif attribute == 'location':
                for location in data['location']:
                    setattr(event, location, data['location'][location])
            elif attribute == 'from':
                event.startTime=data["from"]
            elif attribute == 'to':
                event.endTime = data['to']
            else:
                api.abort(400, 'Wrong payload: some parameters do not exist.')

        event.last_update=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.session.commit()
        return {'id': event.id, 'last-update':datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                '_links': {"self": {'href': f'/events/{event.id}'}
                          }
                }

DAO = eventDAO()

##### Endpoint 1
@ns.route('/<int:id>')
class Event(Resource):
    @api.doc('get_event')
    @api.response(200, 'OK')
    @api.response(404, 'Invalid id')
    def get(self, id):
        return DAO.get(id), 200

    @api.doc('delete_event')
    @api.response(200, 'OK')
    @api.response(404, 'Invalid id')
    def delete(self, id):
        DAO.delete(id)
        return { 
            "message" :f"The event with id {id} was removed from the database!",
            "id": id}, 200

    @api.doc('update_event')
    @api.response(200, 'OK', postResponse)
    @api.response(404, 'Invalid id')
    @api.response(400, 'Invalid payload')
    @api.expect(event)
    def patch(self, id):
        return DAO.update(id, api.payload),200

##### Endpoint 2
######################### 5. GET All ###########################
@ns.route('/')
class EventList(Resource):
    @api.doc('list_all_events')
    @api.doc('list_filtered_events')
    @api.param('order', 'Sort events by criteria (e.g., +id,-name,+datetime). No space allowed between each comma.', required=True, default='+id')
    @api.param('page', 'Page number for pagination (must be a positive integer)', required=True, default=1, type=int)
    @api.param('size', 'Number of events per page (must be a positive integer)', required=True, default=10, type=int)
    @api.param('filter', 'Attributes to show for each event (Any one of combination of: id, name, date, from, to, and location). No spaces allowed between each comma.', required=True, default='id,name')
    @api.response(200, 'OK')
    @api.response(404, 'Non Existing Page')
    @api.response(400, 'Invalid Parameters')
    def get(self):
        #retrieve the given events
        order = request.args.get('order', '+id')
        page = int(request.args.get('page', 1)) # Current page
        size = int(request.args.get('size', 10)) # Number of events in each page
        filter = request.args.get('filter', 'id,name').split(',') # what to be shown

        available_order = ['id', 'name', 'datetime']

        if size <= 0:
            api.abort(400, 'Cannot show zero or negative number of events in each page.')
        if page <= 0:
            api.abort(400, 'Zero or negative page numbers do not exist.')

        # Sort featured
        sort_criteria = []
        for criteria in order.split(','):
            order_name = criteria[1:]
            if order_name not in available_order:
                api.abort(400, 'Wrong Parameter(s): order must be any one or combination of: id, name, datetime. And no space allowed between each comma.' )
            if criteria[0] == '-':
                if order_name == 'datetime':
                    sort_criteria.append(desc(Model.date))
                    sort_criteria.append(desc(Model.startTime))
                elif order_name in ['id', 'name', 'date', 'startTime', 'endTime']:
                    sort_criteria.append(desc(getattr(Model, order_name)))
            elif criteria[0] == '+':
                if order_name == 'datetime':
                    sort_criteria.append(asc(Model.date))
                    sort_criteria.append(asc(Model.startTime))
                elif order_name in ['id', 'name', 'date', 'startTime', 'endTime']:
                    sort_criteria.append(asc(getattr(Model, order_name)))
            else:
                api.abort(400, 'Wrong Parameter(s): order. (only - or + accept).')

        events = Model.query.order_by(*sort_criteria).all()

        # Calculate the total number of pages
        total_pages = (len(events) + size - 1) // size
        # 404 ERROR if do not have this page nubmer
        if page > total_pages:
            api.abort(404, 'Page parameter exceeds the total number of pages.')

        # pagination feature
        start_index = (page - 1) * size
        end_index = start_index + size
        paginated_events = events[start_index:end_index]

        # Filtering feature
        filtered_events = []
        for event in paginated_events:
            filtered_event = {}
            for attribute in filter:
                if attribute in ['id', 'name', 'date']:
                    filtered_event[attribute] = getattr(event, attribute)
                elif attribute == 'from':
                    filtered_event[attribute] = event.startTime
                elif attribute == 'to':
                    filtered_event[attribute] = event.endTime
                elif attribute == 'location':
                    filtered_event['location'] = {
                        'street': event.street,
                        'suburb': event.suburb,
                        'state': event.state,
                        'post_code': event.post_code
                    }
                else:
                    api.abort(400, 'Wrong Parameter(s): filter must be any one or combination of: id, name, date, from, to, and location). No spaces allowed between each comma.')
            filtered_events.append(filtered_event)

        links = {
            "self": {
                "href": f"/events?order={order}&page={page}&size={size}&filter={','.join(filter)}"
                }
            }
        if page > 1:
            links["previous"] = {
                "href": f"/events?order={order}&page={page-1}&size={size}&filter={','.join(filter)}"
            }

        if page < total_pages:
            links["next"] = {
                "href": f"/events?order={order}&page={page+1}&size={size}&filter={','.join(filter)}"
            }

        response = {
            "page": page,
            "page-size": size,
            "events": filtered_events,
            "_links": links
        }

        return response, 200

    @api.doc('create_event')
    @api.expect(event)
    @api.response(201, 'Event Created', postResponse)
    @api.response(400, 'Invalid Input')
    def post(self):
        return DAO.create(api.payload), 201
    
##### End point 3
####################### 6.STATISTICS ###########################
@ns.route('/statistics')
@api.response(200, 'OK', statsResponse)
class EventStatistics(Resource):
    @api.doc('event_statistics')
    @api.param('format', 'Format of the response (must be json or image)', required=True, default='json')
    @api.response(400, 'Invalid format')
    def get(self):
        format = request.args.get('format', 'json').lower()

        # Today's date
        today = datetime.date.today()
    
        # Current calendar week (today to Sunday)
        week_end = today + datetime.timedelta(days=(6 - today.weekday()))
    
        month_start = today.replace(day=1)
        if month_start.month in [1,3,5,7,8,10,12]:
            month_end = today.replace(day=31)
        elif month_start.month == 2 and month_start.year % 4 == 0:
            month_end = today.replace(day=29)
        elif month_start.month == 2 and month_start.year % 4 != 0:
            month_end = today.replace(day=28)
        else:
            month_end = today.replace(day=30)
        
        if format == 'json':
            # Total number of events
            total_events = Model.query.count()

            # Total number of events in the current calendar week
            total_current_week = Model.query.filter(Model.date.between(today, week_end)).count()

            # Total number of events in the current calendar month
            total_current_month = Model.query.filter(Model.date.between(month_start, month_end)).count()

            # Number of events per day
            per_day_counts = Model.query.with_entities(Model.date, func.count(Model.id)).group_by(Model.date).all()
            per_day_counts_dict = {str(date): count for date, count in per_day_counts}

            # Prepare the response
            response = {
                "total": total_events,
                "total-current-week": total_current_week,
                "total-current-month": total_current_month,
                "per-days": per_day_counts_dict
            }

            return response, 200
        elif format == 'image':
            # Generate the bar chart using matplotlib
            per_day_counts = Model.query.with_entities(Model.date, func.count(Model.id)).group_by(Model.date).all()
    
            dates = [str(date) for date, count in per_day_counts]
            counts = [count for date, count in per_day_counts]
    
            fig, ax = plt.subplots()
            ax.bar(dates, counts)
            ax.set_xlabel('Dates')
            ax.set_ylabel('Number of Events')
            ax.set_title('Number of Events per Day')
    
            # Save the chart as an image in memory
            img_data = io.BytesIO()
            fig.savefig(img_data, format='png')
            img_data.seek(0)
    
            # Send the image as a response
            return send_file(img_data, mimetype='image/png', as_attachment=True, download_name='event_statistics.png')
        
        
        else:
            return {"error": "Invalid format specified."}, 400

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
