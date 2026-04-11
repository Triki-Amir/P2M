# from flask import Flask


# def create_app():
#     app = Flask(__name__)
   
#     # Database configuration
#     app.config['DATABASE_URL'] = 'postgresql://user:password@localhost:5432/mydatabase'
   
#     @app.route('/health')
#     def health():
#         return {'status': 'healthy'}, 200
   
#     @app.route('/tables')
#     def tables():
#         return {'tables': ['documents']}, 200
   
#     return app
