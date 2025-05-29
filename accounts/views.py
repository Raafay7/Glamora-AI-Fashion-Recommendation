import os
import json
import uuid
import math
import stripe
import random
from io import BytesIO
from xhtml2pdf import pisa
from django.views import View
from products.models import *
from django.urls import reverse
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from home.models import ShippingAddress
from django.contrib.auth.models import User
from django.template.loader import get_template
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.utils.http import url_has_allowed_host_and_scheme
from django.shortcuts import redirect, render, get_object_or_404
from accounts.models import Profile, Cart, CartItem, Order, OrderItem, Product
from accounts.forms import UserUpdateForm, UserProfileForm, ShippingAddressForm, CustomPasswordChangeForm, UserPreferenceForm

stripe.api_key = settings.STRIPE_SECRET_KEY

def login_page(request):
    next_url = request.GET.get('next') 
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user_obj = User.objects.filter(username=username)

        if not user_obj.exists():
            messages.warning(request, 'Account not found!')
            return HttpResponseRedirect(request.path_info)

        user_obj = authenticate(username=username, password=password)
        if user_obj:
            login(request, user_obj)
            messages.success(request, 'Login Successfull.')

            profile = Profile.objects.get(user=user_obj)
            if not profile.style_quiz_completed:
                return redirect('style_quiz') 

            if url_has_allowed_host_and_scheme(url=next_url,allowed_hosts=request.get_host()):
                return redirect(next_url)
            else:
                return redirect('index')

        messages.warning(request, 'Invalid credentials.')
        return HttpResponseRedirect(request.path_info)

    return render(request, 'accounts/login.html')


def register_page(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        password = request.POST.get('password')

        user_obj = User.objects.filter(username=username, email=email)

        if user_obj.exists():
            messages.info(request, 'Username or email already exists!')
            return HttpResponseRedirect(request.path_info)

        user_obj = User.objects.create(
            username=username, first_name=first_name, last_name=last_name, email=email)
        user_obj.set_password(password)
        user_obj.save()

        profile = Profile.objects.get(user=user_obj)
        profile.email_token = str(uuid.uuid4())
        profile.save()

        request.session['just_registered'] = True
        messages.success(request,"Registration successful!")
        return redirect('login')

    return render(request, 'accounts/register.html')


@login_required
def user_logout(request):
    logout(request)
    messages.warning(request, "Logged Out Successfully!")
    return redirect('index')


def activate_email_account(request, email_token):
    try:
        user = Profile.objects.get(email_token=email_token)
        user.is_email_verified = True
        user.save()
        messages.success(request, 'Account verification successful.')
        return redirect('login')
    except Exception as e:
        return HttpResponse('Invalid email token.')


@login_required
def add_to_cart(request, uid):
    
    SIZE_MAP = {
    'S': 'Small',
    'M': 'Medium',
    'L': 'Large'
    }

    try:
        variant = request.GET.get('size')
        if not variant:
            user_profile = request.user.profile
            variant = user_profile.clothing_size
            variant = SIZE_MAP.get(variant.upper(), variant)

        product = get_object_or_404(Product, uid=uid)
        cart, _ = Cart.objects.get_or_create(user=request.user, is_paid=False)
        size_variant = get_object_or_404(SizeVariant, size_name=variant)

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart, product=product, size_variant=size_variant)
        if not created:
            cart_item.quantity += 1
            cart_item.save()

        messages.success(request, 'Item added to cart successfully.')

    except Exception as e:
        messages.error(request, f'Error adding item to cart: {str(e)}')

    return redirect(reverse('cart'))


@login_required
def cart(request):
    user = request.user
    cart_obj = Cart.objects.filter(is_paid=False, user=user).first()

    if not cart_obj:
        messages.warning(request, "Your cart is empty. Please add a product to the cart.")
        return redirect(reverse('index'))
    
    profile = Profile.objects.filter(user=user).first()
    if not profile or not profile.shipping_address:
        messages.warning(request, "Please update your shipping address before checkout.")
        return redirect(reverse('profile', kwargs={'username': user.username}))

    if request.method == 'POST':
        coupon_code = request.POST.get('coupon')
        coupon_obj = Coupon.objects.filter(coupon_code__exact=coupon_code, is_expired=False).first()

        if not coupon_obj:
            messages.warning(request, 'Invalid or expired coupon code.')
        elif cart_obj.coupon:
            messages.warning(request, 'A coupon is already applied.')
        elif cart_obj.get_cart_total() < coupon_obj.minimum_amount:
            messages.warning(request, f'Cart total must be at least {coupon_obj.minimum_amount} to use this coupon.')
        else:
            cart_obj.coupon = coupon_obj
            cart_obj.save()
            messages.success(request, 'Coupon applied successfully.')

        return HttpResponseRedirect(request.META.get('HTTP_REFERER', reverse('cart')))
    
    if 'checkout' in request.GET and cart_obj:
        cart_total = cart_obj.get_cart_total_price_after_coupon()
        cart_total_in_paise = int(cart_total * 100)  
        print(f"Cart Total in Paise: {cart_total_in_paise}")

        if cart_total_in_paise < 100:
            messages.warning(
                request, 'Total amount in cart is less than the minimum required amount (1.00 PKR). Please add a product to the cart.')
            return redirect('cart')
        
        line_items = []
        for cart_item in cart_obj.cart_items.all():
            product = cart_item.product
            unit_price = product.price
            
            if cart_item.color_variant:
                unit_price += cart_item.color_variant.price
            if cart_item.size_variant:
                unit_price += cart_item.size_variant.price

            product_name = product.product_name
            if cart_item.size_variant:
                product_name += f" - Size: {cart_item.size_variant.size_name}"
            if cart_item.color_variant:
                product_name += f" - Color: {cart_item.color_variant.color_name}"

            line_items.append({
                'price_data': {
                    'currency': 'pkr',
                    'product_data': {
                        'name': product_name,
                    },
                    'unit_amount': int(unit_price * 100),  # Convert to paise
                },
                'quantity': cart_item.quantity,
            })     

        if cart_obj.coupon:
            line_items.append({
                'price_data': {
                    'currency': 'pkr',
                    'product_data': {
                        'name': f'Discount (Coupon: {cart_obj.coupon.coupon_code})',
                    },
                    'unit_amount': int(cart_obj.coupon.discount_amount * 100),  
                },
                'quantity': 1,
            })

        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                shipping_address_collection={
                    'allowed_countries': ['PK'],
                },
                customer_email=user.email,
                line_items=line_items,
                mode='payment',
                success_url=request.build_absolute_uri(reverse('success')) + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=request.build_absolute_uri(reverse('cart')),

                metadata={
                'cart_id': str(cart_obj.uid),
                'user_id': str(user.id),
                },
            )

            # Save the session ID to the cart
            cart_obj.stripe_checkout_session_id = checkout_session.id
            cart_obj.save()

            return redirect(checkout_session.url)
            
        except Exception as e:
            messages.error(request, f"Error creating checkout session: {str(e)}")
            return redirect('cart')
        
    context = {
        'cart': cart_obj,
        'quantity_range': range(1, 6),
        'shipping_address': profile.shipping_address if profile else None,
    }

    return render(request, 'accounts/cart.html', context)


@login_required
def success(request):
    """Handle successful payment return from Stripe"""
    session_id = request.GET.get('session_id')
    if not session_id:
        messages.error(request, "Invalid request.")
        return redirect('index')
    
    try:
        # Retrieve the session
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=['payment_intent', 'line_items', 'customer', 'shipping']
        )
        
        # Verify payment status
        if session.payment_status != 'paid':
            messages.error(request, "Payment not completed.")
            return redirect('cart')
        
        # Get the cart
        cart = Cart.objects.filter(stripe_checkout_session_id=session_id).first()
        if not cart:
            messages.error(request, "Order not found.")
            return redirect('index')
        
        # Mark cart as paid
        cart.is_paid = True
        cart.stripe_payment_intent_id = session.payment_intent.id
        cart.save()
        
        shipping_address_text = ""          
        shipping_address = ShippingAddress.objects.filter(user=cart.user, current_address=True).first()

        if shipping_address:
            shipping_address_text = f"{shipping_address.first_name} {shipping_address.last_name}, " \
                            f"{shipping_address.street}, {shipping_address.street_number}, " \
                            f"{shipping_address.city}, {shipping_address.country}, " \
                            f"{shipping_address.zip_code}, {shipping_address.phone}"
        else:
            shipping_address_text = "No shipping address found."
        
        # Create the order
        order = Order.objects.create(
            user=cart.user,
            order_id=session.payment_intent.id if session.payment_intent else None,
            payment_status="Paid",
            shipping_address=shipping_address_text,
            payment_mode="Stripe",
            order_total_price=cart.get_cart_total(),
            coupon=cart.coupon,
            grand_total=cart.get_cart_total_price_after_coupon(),
        )
        
        # Create order items
        for cart_item in cart.cart_items.all():
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                size_variant=cart_item.size_variant,
                color_variant=cart_item.color_variant,
                quantity=cart_item.quantity,
                product_price=cart_item.get_product_price()
            )
        
        context = {'order': order, 'order_id': order.order_id}
        return render(request, 'payment_success/payment_success.html', context)
        
    except Exception as e:
        messages.error(request, f"An error occurred: {str(e)}")
        return redirect('cart')


@require_POST
@login_required
def update_cart_item(request):
    try:
        data = json.loads(request.body)
        cart_item_id = data.get("cart_item_id")
        quantity = int(data.get("quantity"))

        cart_item = CartItem.objects.get(uid=cart_item_id, cart__user=request.user, cart__is_paid=False)
        cart_item.quantity = quantity
        cart_item.save()

        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


def remove_cart(request, uid):
    try:
        cart_item = get_object_or_404(CartItem, uid=uid)
        cart_item.delete()
        messages.success(request, 'Item removed from cart.')

    except Exception as e:
        print(e)
        messages.warning(request, 'Error removing item from cart.')

    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def remove_coupon(request, cart_id):
    cart = Cart.objects.get(uid=cart_id)
    cart.coupon = None
    cart.save()

    messages.success(request, 'Coupon Removed.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

@ensure_csrf_cookie
def style_quiz_view(request):
    """Renders the style quiz page"""
    return render(request, 'accounts/style_quiz.html')


def save_style_quiz(request):
    """Saves the user's style preferences from the quiz"""
    if request.method == 'POST':
        try:
            # Extract data from POST request
            clothing_types = request.POST.get('answer_0', '')
            body_shape = request.POST.get('answer_1', '')
            skin_tone = request.POST.get('answer_2', '')
            clothing_size = request.POST.get('answer_3', '')
            favorite_brands = request.POST.get('answer_4', '')
            budget_range = request.POST.get('answer_5', '')

            # Update Profile model
            profile = Profile.objects.get(user=request.user)
            profile.clothing_types = clothing_types
            profile.body_shape = body_shape
            profile.skin_tone = skin_tone
            profile.clothing_size = clothing_size
            profile.favorite_brands = favorite_brands
            profile.budget_range = budget_range
            profile.style_quiz_completed = True
            profile.save()

            return JsonResponse({'success': True})
        
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request'})


# HTML to PDF Conversion
def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html = template.render(context_dict)
    
    # Generate PDF using xhtml2pdf
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    
    if not pdf.err:
        return result.getvalue()  # Return raw PDF data
    return None


def download_invoice(request, order_id):
    order = Order.objects.filter(order_id=order_id).first()
    
    if not order:
        return HttpResponse("Order not found", status=404)

    order_items = order.order_items.all()
    context = {
        'order': order,
        'order_items': order_items,
    }

    # Generate PDF
    pdf_data = render_to_pdf('accounts/order_pdf_generate.html', context)
    
    if pdf_data:
        # Define file path to save the PDF
        file_path = os.path.join(settings.MEDIA_ROOT, f"invoices/{order_id}.pdf")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        # Save PDF file to disk
        with open(file_path, "wb") as f:
            f.write(pdf_data)

        # Serve the file as a response
        with open(file_path, "rb") as pdf_file:
            response = HttpResponse(pdf_file.read(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="Order_{order_id}.pdf"'
            return response

    return HttpResponse("Error generating PDF", status=400)


@login_required
def profile_view(request, username):
    user_name = get_object_or_404(User, username=username)
    user = request.user
    profile = user.profile

    user_form = UserUpdateForm(instance=user)
    profile_form = UserProfileForm(instance=profile)

    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=user)
        profile_form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    context = {
        'user_name': user_name,
        'user_form': user_form,
        'profile_form': profile_form
    }

    return render(request, 'accounts/profile.html', context)


@login_required
def preferences(request):
    user = request.user
    profile = user.profile
    preference_form = UserPreferenceForm(instance=profile)

    if request.method == 'POST':
        preference_form = UserPreferenceForm(request.POST, instance=profile)
        if preference_form.is_valid():
            preference_form.save()
            messages.success(request, 'Your preferences has been updated successfully!')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    context = {
        'form': preference_form
    }

    return render(request, 'accounts/preferences.html', context)


@login_required
def change_password(request):
    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Important!
            messages.success(request, 'Your password was successfully updated!')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
        else:
            messages.warning(request, 'Please correct the error below.')
    else:
        form = CustomPasswordChangeForm(request.user)
    return render(request, 'accounts/change_password.html', {'form': form})


@login_required
def update_shipping_address(request):
    user = request.user
    shipping_address = ShippingAddress.objects.filter(
        user=user, current_address=True).first()

    if request.method == 'POST':
        form = ShippingAddressForm(request.POST, instance=shipping_address)
        if form.is_valid():
            shipping_address = form.save(commit=False)
            shipping_address.user = request.user
            shipping_address.current_address = True
            shipping_address.save()
            profile = Profile.objects.filter(user=user).first()
            if profile:
                profile.shipping_address = shipping_address
                profile.save()
            messages.success(request, "The Address Has Been Successfully Saved/Updated!")
            form = ShippingAddressForm()
        else:
            form = ShippingAddressForm(request.POST, instance=shipping_address)
    else:
        form = ShippingAddressForm(instance=shipping_address)
    return render(request, 'accounts/shipping_address_form.html', {'form': form})


# Order history view
@login_required
def order_history(request):
    orders = Order.objects.filter(user=request.user).order_by('-order_date')
    return render(request, 'accounts/order_history.html', {'orders': orders})


# Create an order view
def create_order(cart):
    order, created = Order.objects.get_or_create(
        user=cart.user,
        order_id=cart.stripe_payment_intent_id,
        payment_status="Paid",
        shipping_address=cart.user.profile.shipping_address,
        payment_mode="Stripe",
        order_total_price=cart.get_cart_total(),
        coupon=cart.coupon,
        grand_total=cart.get_cart_total_price_after_coupon(),
    )

    # Create OrderItem instances for each item in the cart
    cart_items = CartItem.objects.filter(cart=cart)
    for cart_item in cart_items:
        OrderItem.objects.get_or_create(
            order=order,
            product=cart_item.product,
            size_variant=cart_item.size_variant,
            color_variant=cart_item.color_variant,
            quantity=cart_item.quantity,
            product_price=cart_item.get_product_price()
        )

    return order


# Order Details view
@login_required
def order_details(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    order_items = OrderItem.objects.filter(order=order)
    context = {
        'order': order,
        'order_items': order_items,
        'order_total_price': sum(item.get_total_price() for item in order_items),
        'coupon_discount': order.coupon.discount_amount if order.coupon else 0,
        'grand_total': order.get_order_total_price()
    }
    return render(request, 'accounts/order_details.html', context)


# Delete user account feature
@login_required
def delete_account(request):
    if request.method == 'POST':
        user = request.user
        logout(request)
        user.delete()
        messages.success(request, "Your account has been deleted successfully.")
        return redirect('index')


#recommendations

class RecommendationEngine:
    # Color recommendations based on skin tone
    SKIN_TONE_COLORS = {
        'wheatish': {
            'best': ['navy blue', 'emerald green', 'burgundy', 'coral', 'turquoise', 'golden yellow', 'cream', 'burnt orange'],
            'avoid': ['pale pink', 'washed out colors', 'very light pastels']
        },
        'tan': {
            'best': ['deep purple', 'royal blue', 'forest green', 'crimson', 'gold', 'chocolate brown', 'ivory', 'terracotta'],
            'avoid': ['neon colors', 'very bright yellows', 'pale green']
        },
        'brown': {
            'best': ['bright white', 'electric blue', 'hot pink', 'lime green', 'orange', 'yellow', 'red', 'purple'],
            'avoid': ['muddy browns', 'khaki', 'olive drab']
        },
        'light': {
            'best': ['soft pastels', 'light blue', 'lavender', 'pink', 'mint green', 'peach', 'baby blue', 'rose gold'],
            'avoid': ['very dark colors', 'harsh neons', 'muddy colors']
        }
    }

    # Define 10 diverse clusters
    CLUSTER_DEFINITIONS = {
        0: {
            'name': 'Professional Executive',
            'preferences': ['formal', 'structured', 'office', 'business', 'elegant'],
            'occasions': ['Interview', 'Work', 'Formal Event'],
            'colors': ['navy', 'black', 'grey', 'white', 'burgundy'],
            'styles': ['blazer', 'suit', 'formal shirt', 'trouser']
        },
        1: {
            'name': 'Casual Weekend',
            'preferences': ['casual', 'comfortable', 'relaxed', 'everyday'],
            'occasions': ['Casual Outing', 'Home'],
            'colors': ['denim', 'white', 'grey', 'beige', 'pastels'],
            'styles': ['jeans', 't-shirt', 'casual dress', 'sneakers']
        },
        2: {
            'name': 'Social Butterfly',
            'preferences': ['social', 'trendy', 'fashionable', 'stylish'],
            'occasions': ['Party', 'Date Night', 'Mall'],
            'colors': ['bright', 'bold', 'trendy colors'],
            'styles': ['dress', 'heels', 'accessories', 'statement pieces']
        },
        3: {
            'name': 'Comfort Seeker',
            'preferences': ['comfort', 'loose', 'breathable', 'soft'],
            'occasions': ['Home', 'Casual Outing'],
            'colors': ['neutral', 'earth tones', 'soft colors'],
            'styles': ['loose tops', 'comfortable pants', 'soft fabrics']
        },
        4: {
            'name': 'Seasonal Fashionista',
            'preferences': ['seasonal', 'weather-appropriate', 'trendy'],
            'occasions': ['varies by season'],
            'colors': ['seasonal colors'],
            'styles': ['seasonal appropriate', 'layered', 'weather-specific']
        },
        5: {
            'name': 'Traditional Elegance',
            'preferences': ['traditional', 'cultural', 'elegant', 'classic'],
            'occasions': ['Wedding', 'Festive', 'Cultural Events'],
            'colors': ['gold', 'red', 'maroon', 'traditional colors'],
            'styles': ['saree', 'kurta', 'traditional wear', 'ethnic']
        },
        6: {
            'name': 'Outdoor Adventurer',
            'preferences': ['outdoor', 'active', 'practical', 'durable'],
            'occasions': ['Outdoor', 'Garden', 'Beach'],
            'colors': ['earth tones', 'practical colors'],
            'styles': ['practical wear', 'weather-resistant', 'comfortable']
        },
        7: {
            'name': 'Romantic Dreamer',
            'preferences': ['romantic', 'feminine', 'soft', 'delicate'],
            'occasions': ['Date Night', 'Dinner', 'Special occasions'],
            'colors': ['pastels', 'soft pinks', 'romantic colors'],
            'styles': ['flowing dresses', 'soft fabrics', 'feminine cuts']
        },
        8: {
            'name': 'Urban Chic',
            'preferences': ['modern', 'urban', 'edgy', 'contemporary'],
            'occasions': ['University', 'Mall', 'Trendy venues'],
            'colors': ['black', 'white', 'bold accents'],
            'styles': ['modern cuts', 'sleek designs', 'urban fashion']
        },
        9: {
            'name': 'Versatile Minimalist',
            'preferences': ['versatile', 'minimal', 'classic', 'timeless'],
            'occasions': ['Multiple occasions', 'Work', 'Casual'],
            'colors': ['neutral palette', 'classic colors'],
            'styles': ['capsule wardrobe', 'mix and match', 'timeless pieces']
        }
    }

    @staticmethod
    def encode_user_profile(profile_dict):
        """One-hot encode user profile"""
        encoded = {}
        
        categories = {
            'body_shape': ['Triangle', 'Rectangle', 'Hourglass', 'Oval'],
            'clothing_type': ['Social', 'Casual', 'Workwear', 'Maternity'],
            'skin_tone': ['Wheatish', 'Tan', 'Brown', 'Light'],
            'location_tag': ['Home', 'Outdoor', 'Office', 'Restaurant', 'University', 'Mall', 'Beach', 'Garden'],
            'occasion_tag': ['Dinner', 'Wedding', 'Date Night', 'Formal Event', 'Interview', 'Party', 'Work', 'Casual Outing'],
            'seasonal_tag': ['Summer', 'Winter', 'Spring', 'Fall', 'Festive', 'Monsoon'],
        }
        
        for category, options in categories.items():
            for option in options:
                key = f"{category}_{option.replace(' ', '_')}"
                encoded[key] = 1 if profile_dict.get(category) == option else 0
        
        return encoded

    @staticmethod
    def extract_advanced_keywords(prompt):
        """Advanced keyword extraction from user prompt with enhanced context understanding"""
        text = prompt.lower()
        extracted_data = {
            'occasion_tag': None,
            'location_tag': None,
            'seasonal_tag': None,
            'keywords': [],
            'colors': [],
            'style_preferences': [],
            'mood_keywords': [],
            'fabric_preferences': [],
            'fit_preferences': []
        }
        
        # Enhanced keyword maps with more synonyms and context
        keyword_maps = {
            'occasions': {
                'dinner': ['dinner', 'dining', 'restaurant', 'meal', 'eating out', 'fine dining', 'lunch'],
                'wedding': ['wedding', 'marriage', 'ceremony', 'reception', 'bride', 'groom', 'bridal'],
                'date night': ['date', 'romantic', 'dating', 'night out', 'special evening', 'romance'],
                'formal event': ['formal', 'gala', 'black tie', 'elegant', 'sophisticated', 'ceremony'],
                'interview': ['interview', 'job', 'professional meeting', 'work meeting', 'career'],
                'party': ['party', 'celebration', 'festive', 'birthday', 'anniversary', 'bash', 'gathering'],
                'work': ['work', 'office', 'professional', 'business', 'corporate', 'workplace'],
                'casual outing': ['casual', 'hangout', 'friends', 'relaxed', 'informal', 'weekend', 'chill']
            },
            'locations': {
                'outdoor': ['outdoor', 'outside', 'park', 'garden', 'picnic', 'nature', 'fresh air'],
                'home': ['home', 'house', 'indoor', 'inside', 'staying in', 'cozy', 'comfortable'],
                'office': ['office', 'workplace', 'work', 'corporate', 'business', 'desk job'],
                'restaurant': ['restaurant', 'cafe', 'diner', 'eatery', 'dining', 'bistro'],
                'university': ['university', 'college', 'campus', 'school', 'academic', 'student'],
                'mall': ['mall', 'shopping', 'store', 'retail', 'market', 'shopping center'],
                'beach': ['beach', 'seaside', 'ocean', 'coastal', 'waterfront', 'sand', 'waves'],
                'garden': ['garden', 'botanical', 'greenhouse', 'park', 'greenery', 'nature']
            },
            'seasons': {
                'summer': ['summer', 'hot', 'sunny', 'beach', 'vacation', 'tropical', 'warm weather'],
                'winter': ['winter', 'cold', 'snow', 'cozy', 'warm', 'holiday', 'chilly'],
                'spring': ['spring', 'fresh', 'bloom', 'mild', 'renewal', 'breezy'],
                'fall': ['fall', 'autumn', 'cool', 'harvest', 'leaves', 'crisp'],
                'festive': ['festive', 'celebration', 'holiday', 'special', 'traditional', 'cultural'],
                'monsoon': ['monsoon', 'rainy', 'wet', 'humid', 'rain', 'drizzle']
            },
            'styles': ['casual', 'formal', 'social', 'workwear', 'loose', 'fitted', 'embroidered', 
                      'elegant', 'trendy', 'classic', 'modern', 'vintage', 'bohemian', 'chic',
                      'minimalist', 'edgy', 'romantic', 'sporty', 'preppy'],
            'clothing': ['shirt', 'pants', 'dress', 'suit', 'trouser', 'abaya', 'saree', 'frock',
                        'blouse', 'skirt', 'jacket', 'kurta', 'jeans', 'top', 'tunic', 'blazer',
                        'cardigan', 'sweater', 'shorts', 'palazzo', 'jumpsuit'],
            'colors': ['black', 'blue', 'green', 'white', 'grey', 'cream', 'lilac', 'red', 'pink',
                      'yellow', 'purple', 'orange', 'brown', 'navy', 'maroon', 'gold', 'silver',
                      'turquoise', 'coral', 'burgundy', 'emerald', 'crimson'],
            'moods': ['confident', 'comfortable', 'stylish', 'professional', 'relaxed', 'bold',
                     'subtle', 'eye-catching', 'understated', 'glamorous', 'sophisticated'],
            'fabrics': ['cotton', 'silk', 'linen', 'wool', 'chiffon', 'satin', 'denim', 'leather',
                       'velvet', 'polyester', 'rayon', 'georgette'],
            'fits': ['loose', 'tight', 'fitted', 'oversized', 'slim', 'regular', 'flowy', 'structured']
        }
        
        # Extract all categories with higher keyword scoring
        for category, subcategories in keyword_maps.items():
            if isinstance(subcategories, dict):
                for main_key, synonyms in subcategories.items():
                    for synonym in synonyms:
                        if synonym in text:
                            if category == 'occasions':
                                extracted_data['occasion_tag'] = main_key.title().replace(' ', ' ')
                            elif category == 'locations':
                                extracted_data['location_tag'] = main_key.title()
                            elif category == 'seasons':
                                extracted_data['seasonal_tag'] = main_key.title()
                            extracted_data['keywords'].append(synonym)
                            break
            else:
                for keyword in subcategories:
                    if keyword in text:
                        extracted_data['keywords'].append(keyword)
                        if category == 'colors':
                            extracted_data['colors'].append(keyword)
                        elif category == 'styles':
                            extracted_data['style_preferences'].append(keyword)
                        elif category == 'moods':
                            extracted_data['mood_keywords'].append(keyword)
                        elif category == 'fabrics':
                            extracted_data['fabric_preferences'].append(keyword)
                        elif category == 'fits':
                            extracted_data['fit_preferences'].append(keyword)
        
        # Remove duplicates and sort by relevance
        for key in ['keywords', 'colors', 'style_preferences', 'mood_keywords', 'fabric_preferences', 'fit_preferences']:
            extracted_data[key] = list(set(extracted_data[key]))
        
        return extracted_data

    @staticmethod
    def get_recommended_colors(skin_tone):
        """Get color recommendations based on skin tone"""
        skin_tone_lower = skin_tone.lower()
        return RecommendationEngine.SKIN_TONE_COLORS.get(skin_tone_lower, {
            'best': ['navy blue', 'white', 'black'],
            'avoid': []
        })

    @staticmethod
    def assign_to_cluster(encoded_profile, extracted_data, user_prompt):
        """Enhanced cluster assignment based on preferences and prompt context"""
        cluster_scores = {}
        
        # Initialize all clusters with base score
        for cluster_id in range(10):
            cluster_scores[cluster_id] = 0
        
        # Score based on extracted keywords and preferences
        prompt_lower = user_prompt.lower()
        
        for cluster_id, cluster_info in RecommendationEngine.CLUSTER_DEFINITIONS.items():
            score = 0
            
            # Check preference matches in prompt
            for pref in cluster_info['preferences']:
                if pref in prompt_lower:
                    score += 2
            
            # Check occasion matches
            for occasion in cluster_info['occasions']:
                if extracted_data.get('occasion_tag') == occasion:
                    score += 3
                elif occasion.lower() in prompt_lower:
                    score += 1
            
            # Check style preferences
            for style in extracted_data.get('style_preferences', []):
                if style in cluster_info['preferences']:
                    score += 2
            
            # Check mood alignment
            for mood in extracted_data.get('mood_keywords', []):
                if mood in cluster_info['preferences']:
                    score += 1.5
            
            # Profile-based scoring
            if encoded_profile.get('clothing_type_Workwear', 0) and cluster_id == 0:
                score += 3
            elif encoded_profile.get('clothing_type_Casual', 0) and cluster_id == 1:
                score += 3
            elif encoded_profile.get('clothing_type_Social', 0) and cluster_id == 2:
                score += 3
            elif encoded_profile.get('clothing_type_Maternity', 0) and cluster_id == 3:
                score += 3
            
            # Seasonal alignment
            if extracted_data.get('seasonal_tag'):
                if cluster_id == 4:  # Seasonal Fashionista
                    score += 2
                elif extracted_data.get('seasonal_tag') == 'Festive' and cluster_id == 5:
                    score += 3
            
            # Location-based scoring
            if extracted_data.get('location_tag') == 'Outdoor' and cluster_id == 6:
                score += 3
            elif extracted_data.get('location_tag') in ['Restaurant', 'Dinner'] and cluster_id == 7:
                score += 2
            elif extracted_data.get('location_tag') in ['University', 'Mall'] and cluster_id == 8:
                score += 2
            
            cluster_scores[cluster_id] = score
        
        # Add randomness to prevent always getting the same cluster
        for cluster_id in cluster_scores:
            cluster_scores[cluster_id] += random.uniform(0, 0.5)
        
        # Return cluster with highest score
        return max(cluster_scores.items(), key=lambda x: x[1])[0]

    @staticmethod
    def cosine_similarity(vec_a, vec_b):
        """Calculate cosine similarity between two vectors"""
        all_keys = set(list(vec_a.keys()) + list(vec_b.keys()))
        
        dot_product = sum(vec_a.get(key, 0) * vec_b.get(key, 0) for key in all_keys)
        
        magnitude_a = math.sqrt(sum(val * val for val in vec_a.values()))
        magnitude_b = math.sqrt(sum(val * val for val in vec_b.values()))
        
        if magnitude_a == 0 or magnitude_b == 0:
            return 0
        
        return dot_product / (magnitude_a * magnitude_b)

    @staticmethod
    def create_product_vector(product, keywords, extracted_data, cluster_id):
        """Create enhanced vector representation of product with cluster-specific weighting"""
        vector = {}
        
        # Product attributes mapping
        attrs = {
            'body_shape': product.body_shapes,
            'clothing_type': product.clothing_types,
            'skin_tone': product.skin_tones,
            'location_tag': product.location_tags,
            'occasion_tag': product.occasion_tags,
            'seasonal_tag': product.seasonal_tags,
        }

        for attr, value in attrs.items():
            if value:
                key = f"{attr}_{value.replace(' ', '_')}"
                vector[key] = 1
        
        # Enhanced keyword matching with different weights
        product_text = f"{product.product_name} {product.product_description} {product.brand}".lower()
        
        # Higher weight for keywords that match cluster preferences
        cluster_info = RecommendationEngine.CLUSTER_DEFINITIONS.get(cluster_id, {})
        cluster_keywords = cluster_info.get('preferences', [])
        
        for keyword in keywords:
            if keyword in product_text:
                # Higher weight if keyword aligns with cluster
                weight = 2.0 if keyword in cluster_keywords else 1.0
                vector[f"keyword_{keyword}"] = weight
        
        # Style preference matching
        for style in extracted_data.get('style_preferences', []):
            if style in product_text:
                vector[f"style_{style}"] = 1.5
        
        # Mood keyword matching
        for mood in extracted_data.get('mood_keywords', []):
            if mood in product_text:
                vector[f"mood_{mood}"] = 1.2
        
        # Fabric preference matching
        for fabric in extracted_data.get('fabric_preferences', []):
            if fabric in product_text:
                vector[f"fabric_{fabric}"] = 1.3
        
        # Color matching with enhanced logic
        if hasattr(product, 'color') and product.color:
            product_color = product.color.lower()
            for color in extracted_data.get('colors', []):
                if color in product_color:
                    vector[f"color_{color}"] = 2.0  # High weight for user-specified colors
        
        return vector

    @staticmethod
    def create_user_vector(profile_dict, keywords, extracted_data, cluster_id):
        """Create enhanced user vector from profile, extracted data, and cluster"""
        encoded = RecommendationEngine.encode_user_profile(profile_dict)
        
        # Get cluster-specific preferences
        cluster_info = RecommendationEngine.CLUSTER_DEFINITIONS.get(cluster_id, {})
        
        # Add keyword preferences with cluster-aware weighting
        for keyword in keywords:
            weight = 2.0 if keyword in cluster_info.get('preferences', []) else 1.0
            encoded[f"keyword_{keyword}"] = weight
        
        # Add style preferences
        for style in extracted_data.get('style_preferences', []):
            encoded[f"style_{style}"] = 1.5
        
        # Add mood preferences
        for mood in extracted_data.get('mood_keywords', []):
            encoded[f"mood_{mood}"] = 1.2
        
        # Add fabric preferences
        for fabric in extracted_data.get('fabric_preferences', []):
            encoded[f"fabric_{fabric}"] = 1.3
        
        # Add color preferences based on skin tone
        skin_tone = profile_dict.get('skin_tone', 'Wheatish')
        recommended_colors = RecommendationEngine.get_recommended_colors(skin_tone)
        
        for color in recommended_colors['best']:
            encoded[f"recommended_color_{color.replace(' ', '_')}"] = 1.2
        
        # Higher weight for user-specified colors
        for color in extracted_data.get('colors', []):
            encoded[f"color_{color}"] = 2.0
        
        # Add cluster-specific preferences
        for pref in cluster_info.get('preferences', []):
            encoded[f"cluster_pref_{pref}"] = 1.5
        
        return encoded

    @staticmethod
    def filter_by_price_range(products, price_range):
        """Filter products by price range"""
        if not price_range or price_range == 'Any':
            return products
        
        ranges = {
            'Budget': (0, 3000),
            'Midrange': (3000, 5000),
            'Premium': (5000, 8000),
            'Varies': (8000, float('inf'))
        }
        
        min_price, max_price = ranges.get(price_range, (0, float('inf')))
        return products.filter(price__gte=min_price, price__lt=max_price)

    @staticmethod
    def get_match_reasons(product, profile_dict, extracted_data, keywords, cluster_id):
        """Get detailed reasons why product matches user preferences"""
        
        # Dynamic defaults based on extracted data
        defaults = {
            'body_shape': 'Hourglass',
            'clothing_type': 'Workwear',
            'skin_tone': 'Wheatish',
            'occasion_tag': extracted_data.get('occasion_tag', 'Dinner'),
            'seasonal_tag': extracted_data.get('seasonal_tag', 'Summer'),
            'location_tag': extracted_data.get('location_tag', 'Outdoor')
        }

        def get_value(key):
            return str(profile_dict.get(key) or defaults[key]).strip().lower()
        
        def safe_match(val1, val2):
            if not val1 or not val2:
                return False
            return str(val1).strip().lower() == str(val2).strip().lower()

        reasons = []
        cluster_info = RecommendationEngine.CLUSTER_DEFINITIONS.get(cluster_id, {})

        # Cluster-specific matching
        reasons.append(f"Matches your {cluster_info.get('name', 'style')} preference")

        # Enhanced matching logic
        if safe_match(product.body_shapes, get_value('body_shape')):
            reasons.append(f"Perfect fit for {get_value('body_shape')} body shape")

        if safe_match(product.clothing_types, get_value('clothing_type')):
            reasons.append(f"Matches your {get_value('clothing_type')} style preference")

        # Skin tone and color matching
        if safe_match(product.skin_tones, get_value('skin_tone')):
            skin_tone = get_value('skin_tone')
            recommended_colors = RecommendationEngine.get_recommended_colors(skin_tone)
            reasons.append(f"Complements your {skin_tone} skin tone")

        # Enhanced keyword matching
        product_text = f"{product.product_name or ''} {product.product_description or ''}".lower()
        
        # Priority keywords from prompt
        priority_keywords = extracted_data.get('style_preferences', []) + extracted_data.get('mood_keywords', [])
        for keyword in priority_keywords:
            if keyword in product_text:
                reasons.append(f'Perfect match for your "{keyword}" style')
                break

        # Regular keyword matching
        for keyword in keywords[:3]:  # Top 3 keywords
            if keyword in product_text:
                reasons.append(f'Matches your search for "{keyword}"')
                break

        # Occasion/location matching
        if safe_match(product.occasion_tags, get_value('occasion_tag')):
            reasons.append(f"Perfect for {get_value('occasion_tag')} occasions")
        elif safe_match(product.location_tags, get_value('location_tag')):
            reasons.append(f"Great for {get_value('location_tag')} settings")

        return reasons[:4]  # Limit to 4 most relevant reasons

    @staticmethod
    def add_diversity_boost(scored_products, user_vector, cluster_id):
        """Add diversity to recommendations to avoid repetitive results"""
        if len(scored_products) <= 6:
            return scored_products
        
        # Group by similar attributes to identify clusters
        attribute_groups = {}
        for i, product in enumerate(scored_products):
            # Create a key based on major attributes
            key = f"{product.get('clothing_type', '')}-{product.get('occasion_tag', '')}-{product.get('brand', '')}"
            if key not in attribute_groups:
                attribute_groups[key] = []
            attribute_groups[key].append((i, product))
        
        # Select diverse products
        diverse_products = []
        used_groups = set()
        
        # First, add top product from each group
        for group_key, products in attribute_groups.items():
            if len(diverse_products) < 6:
                # Sort by similarity within group
                products.sort(key=lambda x: x[1]['similarity'], reverse=True)
                diverse_products.append(products[0][1])
                used_groups.add(group_key)
        
        # Fill remaining slots with highest similarity products not yet included
        remaining_slots = 6 - len(diverse_products)
        if remaining_slots > 0:
            added_indices = {p.get('id', hash(str(p))) for p in diverse_products}
            for product in scored_products:
                if remaining_slots <= 0:
                    break
                product_id = product.get('id', hash(str(product)))
                if product_id not in added_indices:
                    diverse_products.append(product)
                    remaining_slots -= 1
        
        return diverse_products[:6]


@login_required
def recommendation_page(request):
    """Render the recommendation page"""
    try:
        user_preferences = Profile.objects.get(user=request.user)
        has_preferences = True
    except Profile.DoesNotExist:
        has_preferences = False
        user_preferences = None
    
    context = {
        'has_preferences': has_preferences,
        'user_preferences': user_preferences,
    }
    
    return render(request, 'accounts/recommendation_page2.html', context)


class GenerateRecommendationsView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            user_prompt = data.get('prompt', '').strip()
            
            if not user_prompt:
                return JsonResponse({'error': 'Prompt is required'}, status=400)
            
            # Get user preferences from database
            try:
                user_prefs = Profile.objects.get(user=request.user)
            except Profile.DoesNotExist:
                return JsonResponse({'error': 'User preferences not found'}, status=404)
            
            # Extract advanced data from prompt
            engine = RecommendationEngine()
            extracted_data = engine.extract_advanced_keywords(user_prompt)
            
            # Build enhanced profile dictionary with dynamic defaults
            profile_dict = {
                'body_shape': user_prefs.body_shape,
                'clothing_type': user_prefs.clothing_types,
                'skin_tone': user_prefs.skin_tone,
                'price_range': user_prefs.budget_range,
                'occasion_tag': extracted_data.get('occasion_tag') or 'Dinner',
                'location_tag': extracted_data.get('location_tag') or 'Outdoor',
                'seasonal_tag': extracted_data.get('seasonal_tag') or 'Summer',
            }
            
            # Generate cluster assignment based on prompt and preferences
            keywords = extracted_data['keywords']
            encoded_profile = engine.encode_user_profile(profile_dict)
            cluster = engine.assign_to_cluster(encoded_profile, extracted_data, user_prompt)
            
            # Create user vector with cluster information
            user_vector = engine.create_user_vector(profile_dict, keywords, extracted_data, cluster)
            
            # Get recommended colors for user's skin tone
            recommended_colors = engine.get_recommended_colors(profile_dict['skin_tone'])
            
            # Get products and filter by price range
            products = Product.objects.filter().prefetch_related('product_images')
            filtered_products = engine.filter_by_price_range(products, profile_dict.get('price_range'))

            # Calculate similarities and score products
            scored_products = []
            cluster_info = RecommendationEngine.CLUSTER_DEFINITIONS.get(cluster, {})
            
            for product in filtered_products:
                product_vector = engine.create_product_vector(product, keywords, extracted_data, cluster)
                similarity = engine.cosine_similarity(user_vector, product_vector)
                
                # Enhanced boost calculation with cluster-specific logic
                boost = 0
                
                # Basic attribute matching
                if product.body_shapes == profile_dict.get('body_shape'):
                    boost += 0.3
                if product.clothing_types == profile_dict.get('clothing_type'):
                    boost += 0.25
                if product.skin_tones == profile_dict.get('skin_tone'):
                    boost += 0.2
                if product.location_tags == profile_dict.get('location_tag'):
                    boost += 0.15
                if product.occasion_tags == profile_dict.get('occasion_tag'):
                    boost += 0.25
                if product.seasonal_tags == profile_dict.get('seasonal_tag'):
                    boost += 0.15
                
                # Cluster-specific boost
                product_text = f"{product.product_name} {product.product_description}".lower()
                for cluster_pref in cluster_info.get('preferences', []):
                    if cluster_pref in product_text:
                        boost += 0.3
                        break
                
                # Enhanced keyword matching with priority
                priority_keywords = extracted_data.get('style_preferences', []) + extracted_data.get('mood_keywords', [])
                
                # Priority keyword boost (higher weight)
                for keyword in priority_keywords:
                    if keyword in product_text:
                        boost += 0.4
                
                # Regular keyword boost
                regular_keyword_matches = 0
                for keyword in keywords:
                    if keyword in product_text and keyword not in priority_keywords:
                        regular_keyword_matches += 1
                boost += regular_keyword_matches * 0.15
                
                # Color matching boost
                if hasattr(product, 'color') and product.color:
                    product_color = product.color.lower()
                    # User-specified colors get highest boost
                    for user_color in extracted_data.get('colors', []):
                        if user_color in product_color:
                            boost += 0.5
                            break
                    else:
                        # Recommended colors get moderate boost
                        for rec_color in recommended_colors['best']:
                            if rec_color in product_color:
                                boost += 0.2
                                break
                
                # Fabric preference boost
                for fabric in extracted_data.get('fabric_preferences', []):
                    if fabric in product_text:
                        boost += 0.2
                
                # Brand diversity boost (slight penalty for overused brands)
                brand_penalty = 0
                if hasattr(product, 'brand') and product.brand:
                    # This would ideally track brand frequency in previous recommendations
                    # For now, we'll add slight randomization
                    brand_penalty = random.uniform(0, 0.1)
                
                final_score = similarity + boost - brand_penalty
                
                # Get match reasons
                match_reasons = RecommendationEngine.get_match_reasons(
                    product, profile_dict, extracted_data, keywords, cluster
                )

                # Get product images
                product_images = []
                for img in product.product_images.all():
                    product_images.append({
                        'url': img.image.url if img.image else '',
                        'alt': product.product_name
                    })

                scored_products.append({
                    'name': product.product_name,
                    'description': product.product_description,
                    'price': float(product.price),
                    'brand': product.brand,
                    'body_shape': product.body_shapes,
                    'clothing_type': product.clothing_types,
                    'skin_tone': product.skin_tones,
                    'location_tag': product.location_tags,
                    'occasion_tag': product.occasion_tags,
                    'seasonal_tag': product.seasonal_tags,
                    'color': getattr(product, 'color', None),
                    'similarity': final_score,
                    'match_reasons': match_reasons,
                    'images': product_images,
                    'slug': product.slug,
                    'cluster_match': cluster,
                })
            
            # Sort by similarity score
            scored_products.sort(key=lambda x: x['similarity'], reverse=True)
            
            # Apply diversity boost to avoid repetitive recommendations
            diverse_products = engine.add_diversity_boost(scored_products, user_vector, cluster)
            
            # If we still don't have enough diversity, add some random high-scoring products
            if len(diverse_products) < 6 and len(scored_products) > 6:
                used_ids = {p['id'] for p in diverse_products}
                remaining_products = [p for p in scored_products if p['id'] not in used_ids]
                
                # Add products with different attributes
                for product in remaining_products:
                    if len(diverse_products) >= 6:
                        break
                    
                    # Check if this product adds diversity
                    is_diverse = True
                    for existing in diverse_products:
                        # If too similar to existing products, skip
                        if (product['brand'] == existing['brand'] and 
                            product['clothing_type'] == existing['clothing_type'] and
                            product['occasion_tag'] == existing['occasion_tag']):
                            is_diverse = False
                            break
                    
                    if is_diverse:
                        diverse_products.append(product)
            
            # Ensure we have exactly 6 recommendations
            final_recommendations = diverse_products[:6]
            
            # Add some randomization to prevent identical results for similar prompts
            if len(final_recommendations) == 6:
                # Slightly shuffle the middle products (keep top 2 and bottom 1 stable)
                if len(final_recommendations) > 3:
                    middle_products = final_recommendations[2:5]
                    random.shuffle(middle_products)
                    final_recommendations = (final_recommendations[:2] + 
                                           middle_products + 
                                           final_recommendations[5:])
            
            return JsonResponse({
                'success': True,
                'recommendations': final_recommendations,
                'user_cluster': cluster,
                'cluster_name': cluster_info.get('name', 'Mixed Preferences'),
                'cluster_description': f"Your style matches our {cluster_info.get('name', 'Mixed Preferences')} category",
                'keywords': keywords,
                'extracted_data': extracted_data,
                'recommended_colors': recommended_colors,
                'total_products_analyzed': len(scored_products),
                'diversity_applied': len(diverse_products) != len(scored_products[:6]),
                'prompt_analysis': {
                    'primary_keywords': keywords[:5],
                    'style_preferences': extracted_data.get('style_preferences', []),
                    'mood_keywords': extracted_data.get('mood_keywords', []),
                    'detected_occasion': extracted_data.get('occasion_tag'),
                    'detected_location': extracted_data.get('location_tag'),
                    'detected_season': extracted_data.get('seasonal_tag'),
                }
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)