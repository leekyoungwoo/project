const proxy=require('http-proxy-middleware');

module.exports = function(app) {
    app.use(proxy('/api',{
      target:'http://localhost:10000',
      secure: false
    })),
    app.use(proxy('/exec',{
      target:'http://localhost:10000',
      secure: false
    })),
    app.use(proxy('/fdata',{
      target:'http://localhost:10000',
      secure: false
    })),
    app.use(proxy('/socketio',{
      target:'http://localhost:10000',
      secure: false
    })),
    app.use(proxy('/socket.io',{
      target:'http://localhost:10000',
      secure: false
    }))
}