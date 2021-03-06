"""
Bean Counter - Track Your Coffee!
Copyright (C) 2014  BouncyNudibranch (bouncynudibranch@gmail.com)

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""

from flask import render_template, redirect, g, request, url_for
from flask_login import current_user, login_user, logout_user, login_required
from config import BEANS_PER_PAGE, BREWS_PER_PAGE, ROASTS_PER_PAGE, CUPPINGS_PER_PAGE
from app import app, db, login_manager
from app.models import User, Bean, Brew, Roast, Cupping
from app.forms import LoginForm, RegisterForm, BeanPurchaseForm, BrewForm, RoastForm, CuppingForm
from app.util import timestring_to_seconds, seconds_to_timestring, calculate_dtr, calculate_moisture_loss
from decimal import Decimal


@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


@app.before_request
def before_request():
    g.user = current_user


@app.route('/')
def home():
    stats = {
        'users': db.session.query(db.func.count(User.id)).scalar(),
        'beans': db.session.query(db.func.count(Bean.id)).scalar(),
        'brews': db.session.query(db.func.count(Brew.id)).scalar(),
        'roasts': db.session.query(db.func.count(Roast.id)).scalar(),
        'cuppings': db.session.query(db.func.count(Cupping.id)).scalar()
    }
    return render_template('home.html', stats=stats)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if g.user is not None and g.user.is_authenticated():
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is not None:
            if user.verify_password(form.password.data):
                login_user(user)
                return redirect(url_for('home'))
    return render_template('login.html', form=form)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if g.user is not None and g.user.is_authenticated():
        return redirect(url_for('home'))
    form = RegisterForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None:
            user = User(username=form.username.data, password=User.hash_password(form.password.data))
            User.add_user(user)
            login_user(user)
            return redirect(url_for('home'))
    return render_template('register.html', form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/bean/add', methods=['GET', 'POST'])
@app.route('/bean/add/<int:bean_id>', methods=['GET', 'POST'])
@login_required
def bean_add(bean_id=None):
    user = g.user
    form = BeanPurchaseForm()
    if bean_id:
        bean = Bean.query.get(bean_id)
        form.name.data = bean.name
        form.type.data = bean.bean_type
        form.weight.data = bean.weight
        form.purchase_date.data = bean.purchase_date
        form.notes.data = bean.notes
        form.bean_id.data = bean.id
    if form.validate_on_submit():
        form.bean_id.data = int(form.bean_id.data)
        if form.bean_id.data == 0:
            bean = Bean()
        else:
            bean = Bean.query.get(form.bean_id.data)
            if bean.user_id != user.id:
                return redirect(url_for('bean_list'))
        bean.name = form.name.data
        bean.bean_type = form.type.data
        bean.weight = form.weight.data
        bean.purchase_date = form.purchase_date.data
        bean.notes = form.notes.data
        bean.user_id = user.id
        Bean.add_bean(bean)
        return redirect(url_for('bean_list'))
    return render_template('bean_add.html', form=form)


@app.route('/bean/list')
@app.route('/bean/list/<int:page>')
@login_required
def bean_list(page=1):
    user = g.user
    beans = Bean.query.filter_by(user_id=user.id).order_by(Bean.purchase_date.desc()).paginate(
        page, BEANS_PER_PAGE, False)
    return render_template('bean_list.html', beans=beans)


@app.route('/bean/detail/<int:bean_id>')
# @login_required
def bean_detail(bean_id):
    bean = Bean.query.get(bean_id)
    roast_aggregates = bean.get_aggregate_roast_stats()
    return render_template('bean_detail.html', bean=bean, roast_aggregates=roast_aggregates)


@app.route('/bean/delete/<int:bean_id>')
@login_required
def bean_delete(bean_id):
    user = g.user
    bean = Bean.query.get(bean_id)
    try:
        if bean.user_id != user.id:
            return redirect(url_for('bean_list'))
        bean.remove_bean()
    except AttributeError:
        pass
    return redirect(url_for('bean_list'))


@app.route('/brew/add', methods=['GET', 'POST'])
@app.route('/brew/add/<int:brew_id>', methods=['GET', 'POST'])
@login_required
def brew_add(brew_id=None):
    user = g.user
    form = BrewForm()
    form.roast_batch.choices = [(r.id, '%s - %s' % (r.roast_date, r.bean.name)) for r in Roast.query.filter(
        Roast.user_id == user.id, Roast.bean_id > 0).order_by(Roast.roast_date.desc()).limit(10).all()]
    form.roast_batch.choices.append((0, 'N/A'))
    form.bean_id.choices = [(b.id, '%s - %s (%dg)' % (b.purchase_date, b.name, b.weight)) for b in Bean.query.filter_by(
        user_id=user.id).order_by(Bean.purchase_date.desc()).limit(10).all()]
    if brew_id:
        brew = Brew.query.get(brew_id)
        form.roast_batch.data = brew.roast_id
        form.bean_id.data = brew.bean_id
        form.grind_size.data = brew.grind_size
        form.bean_dose.data = Decimal(brew.bean_dose) / 100
        form.water_dose.data = brew.water_dose
        form.extraction_time.data = seconds_to_timestring(brew.extraction_time)
        form.brew_method.data = brew.brew_method
        form.filter_type.data = brew.filter_type
        form.brew_date.data = brew.brew_date
        form.notes.data = brew.notes
        form.brew_id.data = brew.id
    if form.validate_on_submit():
        form.brew_id.data = int(form.brew_id.data)
        if form.brew_id.data == 0:
            brew = Brew()
        else:
            brew = Brew.query.get(form.brew_id.data)
            if brew.user_id != user.id:
                return redirect(url_for('brew_list'))
        brew.grind_size = form.grind_size.data
        brew.bean_dose = int(form.bean_dose.data * 100)
        brew.water_dose = form.water_dose.data
        brew.extraction_time = timestring_to_seconds(form.extraction_time.data)
        brew.brew_method = form.brew_method.data
        brew.filter_type = form.filter_type.data
        brew.brew_date = form.brew_date.data
        brew.notes = form.notes.data
        brew.user_id = user.id
        brew.bean_id = form.bean_id.data
        brew.roast_id = form.roast_batch.data
        Brew.add_brew(brew)
        return redirect(url_for('brew_list'))
    return render_template('brew_add.html', form=form)


@app.route('/brew/list')
@app.route('/brew/list/<int:page>')
@login_required
def brew_list(page=1):
    user = g.user
    brews = Brew.query.filter_by(user_id=user.id).order_by(Brew.brew_date.desc()).paginate(page, BREWS_PER_PAGE, False)
    return render_template('brew_list.html', brews=brews)


@app.route('/brew/detail/<int:brew_id>')
# @login_required
def brew_detail(brew_id):
    brew = Brew.query.get(brew_id)
    return render_template('brew_detail.html', brew=brew)


@app.route('/brew/delete/<int:brew_id>')
@login_required
def brew_delete(brew_id):
    user = g.user
    brew = Brew.query.get(brew_id)
    try:
        if brew.user_id != user.id:
            return redirect(url_for('brew_list'))
        brew.remove_brew()
    except AttributeError:
        pass
    return redirect(url_for('brew_list'))


@app.route('/roast/add', methods=['GET', 'POST'])
@app.route('/roast/add/<int:roast_id>', methods=['GET', 'POST'])
@login_required
def roast_add(roast_id=None):
    user = g.user
    form = RoastForm()
    form.bean_id.choices = [(b.id, '%s - %s (%dg)' % (b.purchase_date, b.name, b.weight)) for b in Bean.query.filter_by(
        user_id=user.id).order_by(Bean.purchase_date.desc()).limit(10).all()]
    if roast_id:
        roast = Roast.query.get(roast_id)
        form.bean_dose.data = Decimal(roast.bean_dose) / 100
        form.drop_temp.data = roast.drop_temp
        form.dry_end_time.data = seconds_to_timestring(roast.dry_end_time)
        form.dry_end_temp.data = roast.dry_end_temp
        form.fc_begin_time.data = seconds_to_timestring(roast.fc_begin_time)
        form.fc_begin_temp.data = roast.fc_begin_temp
        form.fc_end_time.data = seconds_to_timestring(roast.fc_end_time)
        form.fc_end_temp.data = roast.fc_end_temp
        form.sc_begin_time.data = seconds_to_timestring(roast.sc_begin_time)
        form.sc_begin_temp.data = roast.sc_begin_temp
        form.sc_end_time.data = seconds_to_timestring(roast.sc_end_time)
        form.sc_end_temp.data = roast.sc_end_temp
        form.end_time.data = seconds_to_timestring(roast.end_time)
        form.end_temp.data = roast.end_temp
        form.end_weight.data = Decimal(roast.end_weight) / 100
        form.roaster_machine.data = roast.roaster_machine
        form.roast_date.data = roast.roast_date
        form.notes.data = roast.notes
        form.bean_id.data = roast.bean_id
        form.roast_id.data = roast.id
    if form.validate_on_submit():
        form.roast_id.data = int(form.roast_id.data)
        if form.roast_id.data == 0:
            roast = Roast()
        else:
            roast = Roast.query.get(form.roast_id.data)
            if roast.user_id != user.id:
                return redirect(url_for('roast_list'))
        roast.bean_dose = int(form.bean_dose.data * 100)
        roast.drop_temp = form.drop_temp.data
        roast.dry_end_time = timestring_to_seconds(form.dry_end_time.data)
        roast.dry_end_temp = form.dry_end_temp.data
        roast.fc_begin_time = timestring_to_seconds(form.fc_begin_time.data)
        roast.fc_begin_temp = form.fc_begin_temp.data
        roast.fc_end_time = timestring_to_seconds(form.fc_end_time.data)
        roast.fc_end_temp = form.fc_end_temp.data
        roast.sc_begin_time = timestring_to_seconds(form.sc_begin_time.data)
        roast.sc_begin_temp = form.sc_begin_temp.data
        roast.sc_end_time = timestring_to_seconds(form.sc_end_time.data)
        roast.sc_end_temp = form.sc_end_temp.data
        roast.end_time = timestring_to_seconds(form.end_time.data)
        roast.end_temp = form.end_temp.data
        roast.end_weight = int(form.end_weight.data * 100)
        roast.roaster_machine = form.roaster_machine.data
        roast.roast_date = form.roast_date.data
        roast.notes = form.notes.data
        roast.bean_id = form.bean_id.data
        roast.user_id = user.id
        Roast.add_roast(roast)
        return redirect(url_for('roast_list'))
    return render_template('roast_add.html', form=form)


@app.route('/roast/list')
@app.route('/roast/list/<int:page>')
@login_required
def roast_list(page=1):
    user = g.user
    roasts = Roast.query.filter_by(user_id=user.id).order_by(Roast.roast_date.desc()).paginate(
        page, ROASTS_PER_PAGE, False)
    return render_template('roast_list.html', roasts=roasts)


@app.route('/roast/detail/<int:roast_id>')
# @login_required
def roast_detail(roast_id):
    roast = Roast.query.get(roast_id)
    extra_info = {
        'dtr': calculate_dtr(roast.fc_begin_time, roast.end_time),
        'mloss': calculate_moisture_loss(roast.bean_dose, roast.end_weight)
    }
    return render_template('roast_detail.html', roast=roast, extra_info=extra_info)


@app.route('/roast/delete/<int:roast_id>')
@login_required
def roast_delete(roast_id):
    user = g.user
    roast = Roast.query.get(roast_id)
    try:
        if roast.user_id != user.id:
            return redirect(url_for('roast_list'))
        roast.remove_roast()
    except AttributeError:
        pass
    return redirect(url_for('roast_list'))


@app.route('/cupping/list')
@app.route('/cupping/list/<int:page>')
@login_required
def cupping_list(page=1):
    user = g.user
    cuppings = Cupping.query.filter_by(user_id=user.id).order_by(Cupping.datetime.desc()).paginate(
        page, CUPPINGS_PER_PAGE, False)
    return render_template('cupping_list.html', cuppings=cuppings)


@app.route('/cupping/add', methods=['GET', 'POST'])
@app.route('/cupping/add/<int:cupping_id>', methods=['GET', 'POST'])
@login_required
def cupping_add(cupping_id=None):
    user = g.user
    form = CuppingForm()
    form.roast_id.choices = [(r.id, '%s - %s' % (r.roast_date, r.bean.name)) for r in Roast.query.filter(
        Roast.user_id == user.id, Roast.bean_id > 0).order_by(Roast.roast_date.desc()).limit(10).all()]
    form.roast_id.choices.append((0, 'N/A'))
    if cupping_id:
        cupping = Cupping.query.get(cupping_id)
        form.cupping_id.data = cupping.id
        form.roast_id.data = cupping.roast_id
        form.acidity_notes.data = cupping.acidity_notes
        form.aftertaste_notes.data = cupping.aftertaste_notes
        form.aroma_notes.data = cupping.aroma_notes
        form.datetime.data = cupping.datetime
        form.extra_notes.data = cupping.extra_notes
        form.flavour_notes.data = cupping.flavour_notes
        form.mouthfeel_notes.data = cupping.mouthfeel_notes
        form.overall_notes.data = cupping.overall_notes
    if form.validate_on_submit():
        form.cupping_id.data = int(form.cupping_id.data)
        if form.cupping_id.data == 0:
            cupping = Cupping()
        else:
            cupping = Cupping.query.get(form.cupping_id.data)
            if cupping.user_id != user.id:
                return redirect(url_for('cupping_list'))
        cupping.overall_notes = form.overall_notes.data
        cupping.mouthfeel_notes = form.mouthfeel_notes.data
        cupping.flavour_notes = form.flavour_notes.data
        cupping.extra_notes = form.extra_notes.data
        cupping.acidity_notes = form.acidity_notes.data
        cupping.aftertaste_notes = form.aftertaste_notes.data
        cupping.aroma_notes = form.aroma_notes.data
        cupping.datetime = form.datetime.data
        cupping.roast_id = form.roast_id.data
        cupping.user_id = user.id
        Cupping.add_cupping(cupping)
        return redirect(url_for('cupping_list'))
    return render_template('cupping_add.html', form=form)
    
    
@app.route('/cupping/detail/<int:cupping_id>')
def cupping_detail(cupping_id):
    user = g.user
    cupping = Cupping.query.get(cupping_id)
    return render_template('cupping_detail.html', cupping=cupping)
    
    
@app.route('/cupping/delete/<int:cupping_id>')
@login_required
def cupping_delete(cupping_id):
    user = g.user
    cupping = Cupping.query.get(cupping_id)
    try:
        if cupping.user_id != user.id:
            return redirect(url_for('cupping_list'))
        cupping.remove_cupping()
    except AttributeError:
        pass
    return redirect(url_for('cupping_list'))
