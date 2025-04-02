
from django.db import models
from django.contrib.auth.models import User
from base.models import BaseModel
from products.models import Product, ColorVariant, SizeVariant, Coupon
from home.models import ShippingAddress
from django.conf import settings
import os
# Create your models here.


class Profile(BaseModel):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile")
    is_email_verified = models.BooleanField(default=False)
    email_token = models.CharField(max_length=100, null=True, blank=True)
    profile_image = models.ImageField(upload_to='profile', null=True, blank=True)
    bio = models.TextField(null=True, blank=True)
    shipping_address = models.ForeignKey(ShippingAddress, on_delete=models.CASCADE, related_name="shipping_address", null=True, blank=True)

    CLOTHING_TYPE_CHOICES = [
        ('Casual', 'Casual'),
        ('Workwear', 'Workwear'),
        ('Social occasions', 'Social occasions'),
        ('Maternity', 'Maternity'),
    ]
    BODY_SHAPE_CHOICES = [
        ('Hourglass', 'Hourglass – Waist is the narrowest part of the frame'),
        ('Triangle', 'Triangle – Hips are broader than shoulders'),
        ('Rectangle', 'Rectangle – Hips, shoulders, and waist are the same proportion'),
        ('Oval', 'Oval – Hips and shoulders are narrower than waist'),
    ]
    SKIN_TONE_CHOICES = [
        ('Light', 'Light – Very fair or pale'),
        ('Wheatish', 'Wheatish – Fair with warm undertones'),
        ('Medium Tan', 'Medium Tan – Moderate brown with neutral undertones'),
        ('Deep Brown', 'Deep Brown – Dark complexion'),
    ]
    HAIR_COLOR_CHOICES = [
        ('Black', 'Black'),
        ('Brown', 'Brown'),
        ('Dyed', 'Dyed (Blonde, Red, Balayage, etc.)'),
        ('Other', 'Other'),
    ]
    CLOTHING_SIZE_CHOICES = [
        ('S', 'S'),
        ('M', 'M'),
        ('L', 'L'),
        ('XL', 'XL'),
    ]
    BUDGET_RANGE_CHOICES = [
        ('Budget', 'Budget – Affordable brands, local markets'),
        ('Mid-range', 'Mid-range – High-street brands like Sapphire, Khaadi'),
        ('Premium', 'Premium – Luxury brands like Élan, Sania Maskatiya'),
        ('It Varies', 'It Varies'),
    ]
    HEIGHT_CHOICES = [
        ('Under 5\'2\"', 'Under 5\'2\" (Petite)'),
        ('5\'3\" - 5\'6\"', '5\'3\" - 5\'6\" (Average)'),
        ('5\'7\" - 5\'10\"', '5\'7\" - 5\'10\" (Tall)'),
        ('Above 5\'10\"', 'Above 5\'10\"'),
    ]
    FAVORITE_BRANDS_CHOICES = [
        ('Khaadi', 'Khaadi'),
        ('Gul Ahmed', 'Gul Ahmed'),
        ('Sapphire', 'Sapphire'),
        ('Bonanza Satrangi', 'Bonanza Satrangi'),
    ]

    clothing_types = models.CharField(max_length=100, choices=CLOTHING_TYPE_CHOICES, default='Casual')
    height = models.CharField(max_length=50, choices=HEIGHT_CHOICES, default="5'3\" - 5'6\" (Average)")
    body_shape = models.CharField(max_length=100, choices=BODY_SHAPE_CHOICES, default="Rectangle")
    skin_tone = models.CharField(max_length=100, choices=SKIN_TONE_CHOICES, default="Medium Tan")
    hair_color = models.CharField(max_length=50, choices=HAIR_COLOR_CHOICES, default="Black")
    clothing_size = models.CharField(max_length=10, choices=CLOTHING_SIZE_CHOICES, default="M")
    favorite_brands = models.CharField(max_length=255, choices=FAVORITE_BRANDS_CHOICES, blank=True, null=True, default="")
    budget_range = models.CharField(max_length=100, choices=BUDGET_RANGE_CHOICES, default="Mid-range")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # New field
    style_quiz_completed = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username

    def get_cart_count(self):
        return CartItem.objects.filter(cart__is_paid=False, cart__user=self.user).count()
    
    def save(self, *args, **kwargs):
        # Check if the profile image is being updated and profile exists
        if self.pk:  # Only if profile exists
            try:
                old_profile = Profile.objects.get(pk=self.pk)
                if old_profile.profile_image and old_profile.profile_image != self.profile_image:
                    old_image_path = os.path.join(settings.MEDIA_ROOT, old_profile.profile_image.path)
                    if os.path.exists(old_image_path):
                        os.remove(old_image_path)
            except Profile.DoesNotExist:
                # Profile does not exist, so nothing to do
                pass

        super(Profile, self).save(*args, **kwargs)

class Cart(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cart", null=True, blank=True)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    is_paid = models.BooleanField(default=False)
    stripe_checkout_session_id = models.CharField(max_length=100, null=True, blank=True)
    stripe_payment_intent_id = models.CharField(max_length=100, null=True, blank=True)

    def get_cart_total(self):
        cart_items = self.cart_items.all()
        total_price = 0

        for cart_item in cart_items:
            total_price += cart_item.get_product_price()

        return total_price


    def get_cart_total_price_after_coupon(self):
        total = self.get_cart_total()

        if self.coupon and total >= self.coupon.minimum_amount:
            total -= self.coupon.discount_amount
                    
        return total



class CartItem(BaseModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="cart_items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    color_variant = models.ForeignKey(ColorVariant, on_delete=models.SET_NULL, null=True, blank=True)
    size_variant = models.ForeignKey(SizeVariant, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.IntegerField(default=1)

    def get_product_price(self):
        price = self.product.price * self.quantity

        if self.color_variant:
            price += self.color_variant.price
            
        if self.size_variant:
            price += self.size_variant.price
        
        return price


class Order(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    order_id = models.CharField(max_length=100, unique=True)
    order_date = models.DateTimeField(auto_now_add=True)
    payment_status = models.CharField(max_length=100)
    shipping_address = models.TextField(blank=True, null=True)
    payment_mode = models.CharField(max_length=100)
    order_total_price = models.DecimalField(max_digits=10, decimal_places=2)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Order {self.order_id} by {self.user.username}"
    
    def get_order_total_price(self):
        return self.order_total_price


class OrderItem(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="order_items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    size_variant = models.ForeignKey(SizeVariant, on_delete=models.SET_NULL, null=True, blank=True)
    color_variant = models.ForeignKey(ColorVariant, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    product_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)

    def __str__(self):
        return f"{self.product.product_name} - {self.quantity}"
    
    def get_total_price(self):
        # Use the get_product_price method from CartItem
        cart_item = CartItem(
            product=self.product,
            size_variant=self.size_variant,
            color_variant=self.color_variant,
            quantity=self.quantity
        )
        return cart_item.get_product_price()